# ================================================================
#  fix_admin.py
#  Ye script admin ka password database mein fix kar dega
#  
#  Kaise chalao:
#    python fix_admin.py
# ================================================================

import MySQLdb
from werkzeug.security import generate_password_hash

# ── Apna MySQL password yahan daalo (same jo app.py mein hai) ──
DB_HOST     = 'localhost'
DB_USER     = 'root'
DB_PASSWORD = 'yogesh2570'   # ← apna password
DB_NAME     = 'cdgi_booking'

ADMIN_EMAIL    = 'admin@cdgi.edu.in'
ADMIN_PASSWORD = 'admin123'   # ← chahein to naya password set karo

try:
    conn = MySQLdb.connect(
        host=DB_HOST,
        user=DB_USER,
        passwd=DB_PASSWORD,
        db=DB_NAME
    )
    cur = conn.cursor()

    # Naya sahi hash banao
    new_hash = generate_password_hash(ADMIN_PASSWORD)

    # Database mein update karo
    cur.execute(
        "UPDATE admins SET password = %s WHERE email = %s",
        (new_hash, ADMIN_EMAIL)
    )
    conn.commit()

    if cur.rowcount == 0:
        print("❌ Admin record nahi mila! Pehle SQL file se database setup karo.")
    else:
        print("✅ Admin password fix ho gaya!")
        print(f"   Email    : {ADMIN_EMAIL}")
        print(f"   Password : {ADMIN_PASSWORD}")
        print("\nAb admin_login pe in credentials se login karo.")

    cur.close()
    conn.close()

except Exception as e:
    print(f"❌ Error aaya: {e}")
    print("\nCheck karo:")
    print("  1. MySQL chal raha hai?")
    print("  2. DB_PASSWORD sahi hai?")
    print("  3. cdgi_booking database exist karta hai?")