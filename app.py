import os, sqlite3
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, g, Response, jsonify
from flask_login import (
    LoginManager, UserMixin, login_user, login_required, logout_user
)
from werkzeug.security import check_password_hash

from db_maintenance import enable_fk, ensure_indexes
from services import revenue_by_day, kpis as kpis_service, status_mix, daily_summary

# ---- Validation helpers ----
ALLOWED_STATUSES = {"scheduled", "completed", "cancelled"}
def parse_dt(s: str) -> datetime:
    return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")

# ---- Load env (SECRET_KEY, DB_PATH) ----
load_dotenv()
DB_PATH = os.getenv("DB_PATH")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

# -------- DB helpers --------
def get_db():
    if "db" not in g:
        if not DB_PATH:
            raise RuntimeError("DB_PATH is not set. Create a .env file (see .env.example).")
        if not os.path.exists(DB_PATH):
            raise FileNotFoundError(
                f"Database file not found at DB_PATH={DB_PATH}. "
                "Open .env and set an absolute path to clinic.db"
            )
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        enable_fk(conn)
        ensure_indexes(conn)
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

# -------- Exports --------
@app.route("/exports/appointments.csv")
@login_required
def export_appointments_csv():
    db = get_db()
    rows = db.execute("""
        SELECT
          a.appt_id,
          u.name       AS patient,
          p.name       AS provider,
          a.start_ts,
          a.end_ts,
          a.status,
          COALESCE(i.total, 0) AS total
        FROM appointments a
        JOIN users     u ON u.user_id = a.patient_id
        JOIN providers p ON p.provider_id = a.provider_id
        LEFT JOIN invoices i ON i.appt_id = a.appt_id
        ORDER BY a.start_ts DESC, a.appt_id DESC
    """).fetchall()

    headers = ["appt_id","patient","provider","start_ts","end_ts","status","total"]
    lines = [",".join(headers)]
    def cell(x):
        s = str(x) if x is not None else ""
        return '"' + s.replace('"', '""') + '"' if ("," in s or '"' in s or " " in s) else s
    for r in rows:
        lines.append(",".join([cell(r[h]) for h in headers]))
    csv_data = "\n".join(lines)

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=appointments.csv"}
    )

# -------- Auth routes --------
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

# -------- Dashboard / Reports --------
@app.route("/")
@login_required
def dashboard():
    db = get_db()
    labels, revenue = revenue_by_day(db, limit=10)
    k = kpis_service(db)
    status_labels, status_counts = status_mix(db)
    return render_template(
        "clinic_dashboard.html",
        title="Clinic Dashboard",
        labels=labels,
        revenue=revenue,
        kpis=k,
        status_labels=status_labels,
        status_counts=status_counts
    )

@app.route("/reports/daily")
@login_required
def reports_daily():
    db = get_db()
    data = daily_summary(db, days=14)
    labels  = [d["day"] for d in data]
    appts   = [d["appts"] for d in data]
    revenue = [d["revenue"] for d in data]
    return render_template(
        "reports_daily.html",
        title="Daily Report",
        labels=labels, appts=appts, revenue=revenue, rows=data
    )

# NEW: JSON API for daily report
@app.route("/api/reports/daily")
@login_required
def api_reports_daily():
    days = int(request.args.get("days", 14))
    data = daily_summary(get_db(), days=days)  # [{day, appts, revenue}, ...]
    return jsonify(data), 200

# -------- Error pages --------
@app.errorhandler(404)
def _404(e):
    return render_template("error_404.html", title="404"), 404

@app.errorhandler(500)
def _500(e):
    return render_template("error_500.html", title="500"), 500

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
        # ---- Validation (Commit #8) ----
        patient_id = request.form["patient_id"]
        provider_id = request.form["provider_id"]
        start_s = request.form["start_ts"].strip()
        end_s   = request.form["end_ts"].strip()
        status  = request.form["status"].strip().lower()
        try:
            start = parse_dt(start_s)
            end   = parse_dt(end_s)
            assert end > start, "End time must be after start time"
            assert status in ALLOWED_STATUSES, f"Status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}"
        except Exception as ex:
            flash(str(ex))
            appt = {
                "patient_id": int(patient_id),
                "provider_id": int(provider_id),
                "start_ts": start_s,
                "end_ts": end_s,
                "status": status
            }
            return render_template("appointment_form.html", title="New Appointment",
                                   patients=patients, providers=providers, appt=appt)

        db.execute(
            """INSERT INTO appointments(patient_id, provider_id, start_ts, end_ts, status)
               VALUES (?,?,?,?,?)""",
            (patient_id, provider_id, start_s, end_s, status)
        )
        db.commit()
        return redirect(url_for("appointments_list"))

if __name__ == "__main__":
    app.run(debug=True)
