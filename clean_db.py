import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mydb")
KEEP_EMAIL = "abidov012@gmail.com"

engine = create_engine(DATABASE_URL)

with engine.begin() as conn:
    keep = conn.execute(
        text("SELECT id FROM users WHERE email = :email"),
        {"email": KEEP_EMAIL},
    ).fetchone()

    if keep is None:
        print(f"Пользователь {KEEP_EMAIL} не найден в БД!")
        exit(1)

    keep_id = keep[0]
    print(f"Сохраняю пользователя: {KEEP_EMAIL} (id={keep_id})")

    conn.execute(text("DELETE FROM messages"))
    conn.execute(text("DELETE FROM reviews"))
    conn.execute(text("DELETE FROM transactions"))
    conn.execute(text("DELETE FROM order_offers"))
    conn.execute(text("DELETE FROM orders"))
    conn.execute(text("DELETE FROM worker_profiles WHERE user_id != :id"), {"id": keep_id})
    conn.execute(text("DELETE FROM employer_profiles WHERE user_id != :id"), {"id": keep_id})
    conn.execute(text("DELETE FROM users WHERE id != :id"), {"id": keep_id})

    print("База данных очищена.")
    print(f"Остался пользователь: {KEEP_EMAIL}")
