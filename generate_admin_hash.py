# ================================================================
#  File: generate_admin_hash.py
#  Kaam: Admin password ka hash banana
#
#  Kaise chalayein:
#  terminal mein:  python generate_admin_hash.py
#
#  Jo hash aaye use database_setup.sql mein
#  'REPLACE_WITH_HASH_OF_admin123' ki jagah paste karo
# ================================================================

from werkzeug.security import generate_password_hash

password = "admin123"   # ← chahein to apna password change karo

hashed = generate_password_hash(password)

# print("=" * 60)
print(f"Password : {password}")
print(f"Hash     : {hashed}")
# print("=" * 60)
# print()
# print("Ye hash copy karo aur database_setup.sql mein paste karo:")
# print("admins table ke INSERT mein 'REPLACE_WITH_HASH_OF_admin123'")
# print("ki jagah.")
