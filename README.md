# Clinic App

**Quick start (Windows)**
- Python 3.11+
- Setup:  
  `py -m venv .venv && .\.venv\Scripts\Activate && pip install Flask Flask-Login python-dotenv`
- Configure: copy `.env.example` → `.env`, set `DB_PATH` to your absolute path (e.g., `C:\Users\<you>\Desktop\Clinic\clinic.db`)
- Run:  
  `set FLASK_APP=app && set FLASK_DEBUG=1 && flask run` → http://127.0.0.1:5000

**Utilities**
- Seed demo data: `python seed_clinic.py --reset`
- Export CSV: `GET /exports/appointments.csv`
- Daily report JSON: `GET /api/reports/daily?days=14`

**Features**
- Auth, Appointments CRUD, KPIs dashboard, Reports (chart + table), CSV export
