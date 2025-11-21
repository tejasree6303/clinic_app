import os, sqlite3
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH")
conn = sqlite3.connect(DB_PATH)
conn.execute(
    "UPDATE users SET password_hash=? WHERE email=?",
    (generate_password_hash("test123"), "patient1@example.com")
)
conn.commit()
conn.close()
print("Password set → patient1@example.com / test123")