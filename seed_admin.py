from werkzeug.security import generate_password_hash
from db import db

users_col = db["users"]

ADMIN_EMAIL = "admin@nss.com"
ADMIN_PASSWORD = "Admin123"  # change this

def seed_admin():
    existing_admin = users_col.find_one({"role": "admin"})
    if existing_admin:
        print("✅ Admin already exists")
        return

    admin_user = {
        "email": ADMIN_EMAIL,
        "password": generate_password_hash(
            ADMIN_PASSWORD
        ),
        "role": "admin"
    }

    users_col.insert_one(admin_user)

    print("✅ Admin created successfully")


if __name__ == "__main__":
    seed_admin()