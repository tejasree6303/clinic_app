import os, sqlite3, argparse, random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()
DB_PATH = os.getenv("DB_PATH")
if not DB_PATH:
    raise SystemExit("ERROR: DB_PATH missing. Create .env (see .env.example).")
print(f"Using DB at: {DB_PATH}")

parser = argparse.ArgumentParser(description="Seed Clinic demo data")
parser.add_argument("--reset", action="store_true", help="Drop existing rows before seeding")
parser.add_argument("--users", type=int, default=10, help="Number of demo patients")
parser.add_argument("--providers", type=int, default=10, help="Number of providers")
parser.add_argument("--appointments", type=int, default=20, help="Number of appointments")
args = parser.parse_args()

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("PRAGMA foreign_keys = ON;")

def table_exists(name):
    r = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return r is not None

required = ["users", "providers", "appointments", "invoices"]
missing = [t for t in required if not table_exists(t)]
if missing:
    raise SystemExit(f"ERROR: tables missing: {', '.join(missing)}. Run your DB init first.")

if args.reset:
    print("Reset requested → deleting existing rows…")
    c.execute("DELETE FROM invoices")
    c.execute("DELETE FROM appointments")
    c.execute("DELETE FROM providers")
    c.execute("DELETE FROM users")
    conn.commit()

def is_empty(name):
    return c.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] == 0

# Seed users (patients)
if is_empty("users"):
    print(f"Seeding {args.users} patients…")
    base = datetime(2025, 1, 2)
    rows = []
    for i in range(1, args.users + 1):
        rows.append((
            i,
            f"Patient {i}",
            f"patient{i}@example.com",
            generate_password_hash("test123"),
            (base + timedelta(days=i)).strftime("%Y-%m-%d")
        ))
    c.executemany("INSERT INTO users(user_id,name,email,password_hash,created_at) VALUES (?,?,?,?,?)", rows)

# Seed providers
specs = ["Family Medicine","Pediatrics","Dermatology","Cardiology","Ortho","ENT","Ophthalmology","Psychiatry","OB/GYN","Neurology"]
if is_empty("providers"):
    print(f"Seeding {args.providers} providers…")
    rows = []
    for i in range(1, args.providers + 1):
        rows.append((i, f"Dr. Provider {i}", specs[(i-1) % len(specs)], f"Room {100+i}"))
    c.executemany("INSERT INTO providers(provider_id,name,specialty,room) VALUES (?,?,?,?)", rows)

# Seed appointments + invoices
if is_empty("appointments"):
    print(f"Seeding {args.appointments} appointments + invoices…")
    base = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    appt_rows, inv_rows = [], []
    statuses = ["scheduled", "completed", "cancelled"]
    for i in range(1, args.appointments + 1):
        patient_id = ((i - 1) % max(1, args.users)) + 1
        provider_id = ((i - 1) % max(1, args.providers)) + 1
        start = base + timedelta(days=i//3, hours=(i % 3))
        end = start + timedelta(minutes=30)
        status = random.choices(statuses, weights=[6, 3, 1])[0]
        appt_rows.append((i, patient_id, provider_id,
                          start.strftime("%Y-%m-%d %H:%M:%S"),
                          end.strftime("%Y-%m-%d %H:%M:%S"),
                          status))
        subtotal = 100 + (i % 7) * 15
        discount = 5 if i % 5 == 0 else 0
        tax = round(subtotal * 0.08, 2)
        total = round(subtotal - discount + tax, 2)
        inv_status = "paid" if status == "completed" else "unpaid"
        inv_rows.append((i, i, subtotal, discount, tax, total, inv_status))

    c.executemany("""INSERT INTO appointments(appt_id,patient_id,provider_id,start_ts,end_ts,status)
                     VALUES (?,?,?,?,?,?)""", appt_rows)
    c.executemany("""INSERT INTO invoices(inv_id,appt_id,subtotal,discount,tax,total,status)
                     VALUES (?,?,?,?,?,?,?)""", inv_rows)

conn.commit()
print("✅ Seeding complete.")
