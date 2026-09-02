from __future__ import annotations

import getpass
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

from sqlalchemy import select  # noqa: E402

from app.database import db_session, test_database_connection  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password, validate_login_username  # noqa: E402


def create_boss_interactive() -> bool:
    status = test_database_connection()
    if not status["tables_ok"]:
        print("[X] Database đang thiếu bảng:", ", ".join(status["missing_tables"]))
        return False

    with db_session() as db:
        existing = db.scalar(select(User).where(User.role == "BOSS", User.is_active.is_(True)))
        if existing:
            print(f"[i] Đã có BOSS: {existing.full_name} (@{existing.username})")
            print("    Hãy đăng nhập website; BOSS có thể đổi mật khẩu trong giao diện.")
            return True

    print("\n=== TẠO TÀI KHOẢN BOSS ĐẦU TIÊN ===")
    while True:
        try:
            username = validate_login_username(input("Tên đăng nhập BOSS: ").strip())
            break
        except ValueError as exc:
            print("[X]", exc)
    while True:
        full_name = input("Họ tên BOSS: ").strip()
        if full_name:
            break
        print("[X] Họ tên không được để trống")
    while True:
        password = getpass.getpass("Mật khẩu BOSS (tối thiểu 8 ký tự): ")
        confirm = getpass.getpass("Nhập lại mật khẩu: ")
        if password != confirm:
            print("[X] Hai mật khẩu không giống nhau")
            continue
        try:
            password_hash = hash_password(password)
            break
        except ValueError as exc:
            print("[X]", exc)

    with db_session() as db:
        duplicate = db.scalar(select(User.id).where(User.username_normalized == username.lower()))
        if duplicate:
            print("[X] Tên đăng nhập đã tồn tại")
            return False
        boss = User(
            username=username,
            password_hash=password_hash,
            full_name=full_name,
            role="BOSS",
            can_add_accounts=True,
            can_delete_accounts=True,
            can_run_checks=True,
            is_active=True,
        )
        db.add(boss)

    print("[OK] Đã tạo BOSS. Database chỉ lưu chuỗi Argon2id, không lưu mật khẩu gốc.")
    return True


if __name__ == "__main__":
    try:
        raise SystemExit(0 if create_boss_interactive() else 1)
    except Exception as exc:
        print(f"[X] Không thể tạo BOSS: {exc}")
        raise SystemExit(1)

