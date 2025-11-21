import os, sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, g
from flask_login import (
    LoginManager, UserMixin, login_user, login_required, logout_user
)
from werkzeug.security import check_password_hash
from dotenv import load_dotenv

# Load .env (SECRET_KEY, DB_PATH)
load_dotenv()
DB_PATH = os.getenv("DB_PATH")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

# -------- DB helpers --------
def get_db():
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

# -------- Auth setup --------
login_manager = LoginManager(app)
login_manager.login_view = "login"

class User(UserMixin):
    def __init__(self, row):
        self.id = row["user_id"]         # flask-login expects .id
        self.email = row["email"]
        self.name = row["name"]
        self.password_hash = row["password_hash"]

    @staticmethod
    def get_by_id(uid):
        db = get_db()
        r = db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        return User(r) if r else None

    @staticmethod
    def get_by_email(email):
        db = get_db()
        r = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        return User(r) if r else None

@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(user_id)

# -------- Routes --------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        u = User.get_by_email(email)
        if not u:
            flash("No such user.")
        else:
            if check_password_hash(u.password_hash, password):
                login_user(u)
                return redirect(url_for("dashboard"))
            else:
                flash("Wrong password.")
    return render_template("login.html", title="Login")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    db = get_db()
    # revenue by day
    rows = db.execute("""
        SELECT substr(a.start_ts,1,10) AS day,
               ROUND(COALESCE(SUM(i.total),0), 2) AS revenue
        FROM appointments a
        LEFT JOIN invoices i ON i.appt_id = a.appt_id
        GROUP BY day
        ORDER BY day
        LIMIT 10
    """).fetchall()
    labels = [r["day"] for r in rows]
    revenue = [float(r["revenue"]) for r in rows]

    # KPIs
    k = {}
    k["total_revenue"] = db.execute("SELECT ROUND(COALESCE(SUM(total),0),2) FROM invoices").fetchone()[0] or 0
    k["total_appts"]   = db.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] or 0
    avg = db.execute("SELECT ROUND(AVG(total),2) FROM invoices").fetchone()[0]
    k["avg_invoice"]   = avg if avg is not None else 0
    nxt = db.execute("SELECT MIN(start_ts) FROM appointments WHERE datetime(start_ts) >= datetime('now')").fetchone()[0]
    k["next_appt"]     = nxt

    # status mix for donut
    status_rows = db.execute("SELECT status, COUNT(*) AS c FROM appointments GROUP BY status").fetchall()
    status_labels = [r["status"] for r in status_rows]
    status_counts = [r["c"] for r in status_rows]

    return render_template(
        "clinic_dashboard.html",
        title="Clinic Dashboard",
        labels=labels, revenue=revenue,
        kpis=k,
        status_labels=status_labels,
        status_counts=status_counts
    )
# ---------- CRUD: Appointments ----------
@app.route("/appointments")
@login_required
def appointments_list():
    db = get_db()
    appts = db.execute("""
        SELECT a.appt_id, a.start_ts, a.end_ts, a.status,
               u.name AS patient, p.name AS provider
        FROM appointments a
        JOIN users u ON u.user_id = a.patient_id
        JOIN providers p ON p.provider_id = a.provider_id
        ORDER BY a.appt_id
    """).fetchall()
    return render_template("appointments_list.html", title="Appointments", appts=appts)

@app.route("/appointments/new", methods=["GET","POST"])
@login_required
def appointments_new():
    db = get_db()
    patients = db.execute("SELECT user_id, name FROM users ORDER BY user_id").fetchall()
    providers = db.execute("SELECT provider_id, name FROM providers ORDER BY provider_id").fetchall()
    if request.method == "POST":
        patient_id = request.form["patient_id"]
        provider_id = request.form["provider_id"]
        start_ts = request.form["start_ts"].strip()
        end_ts = request.form["end_ts"].strip()
        status = request.form["status"].strip()
        db.execute("""INSERT INTO appointments(patient_id, provider_id, start_ts, end_ts, status)
                      VALUES (?,?,?,?,?)""",
                   (patient_id, provider_id, start_ts, end_ts, status))
        db.commit()
        return redirect(url_for("appointments_list"))
    return render_template("appointment_form.html", title="New Appointment",
                           patients=patients, providers=providers, appt=None)

@app.route("/appointments/<int:appt_id>/edit", methods=["GET","POST"])
@login_required
def appointments_edit(appt_id):
    db = get_db()
    appt = db.execute("SELECT * FROM appointments WHERE appt_id=?", (appt_id,)).fetchone()
    if not appt:
        return "Not found", 404
    patients = db.execute("SELECT user_id, name FROM users ORDER BY user_id").fetchall()
    providers = db.execute("SELECT provider_id, name FROM providers ORDER BY provider_id").fetchall()
    if request.method == "POST":
        patient_id = request.form["patient_id"]
        provider_id = request.form["provider_id"]
        start_ts = request.form["start_ts"].strip()
        end_ts = request.form["end_ts"].strip()
        status = request.form["status"].strip()
        db.execute("""UPDATE appointments
                      SET patient_id=?, provider_id=?, start_ts=?, end_ts=?, status=?
                      WHERE appt_id=?""",
                   (patient_id, provider_id, start_ts, end_ts, status, appt_id))
        db.commit()
        return redirect(url_for("appointments_list"))
    return render_template("appointment_form.html", title="Edit Appointment",
                           patients=patients, providers=providers, appt=appt)

@app.route("/appointments/<int:appt_id>/delete", methods=["POST"])
@login_required
def appointments_delete(appt_id):
    db = get_db()
    db.execute("DELETE FROM appointments WHERE appt_id=?", (appt_id,))
    db.commit()
    return redirect(url_for("appointments_list"))

if __name__ == "__main__":
    app.run(debug=True)