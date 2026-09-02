from __future__ import annotations

import getpass
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def env_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_env(database_url: str) -> None:
    content = (
        "# File này chứa secret thật, không đưa lên GitHub.\n"
        f"DATABASE_URL={env_quote(database_url)}\n"
        f"SESSION_SECRET={env_quote(secrets.token_urlsafe(48))}\n"
        "APP_ENV=development\n"
        "COOKIE_SECURE=false\n"
        "PROXY_MODE=direct\n"
    )
    ENV_PATH.write_text(content, encoding="utf-8")


def collect_database_url() -> str:
    print("Dán URI Session pooler cổng 5432. Nội dung được ẩn khi dán.")
    uri = getpass.getpass("DATABASE URL: ").strip()
    if not uri.startswith(("postgresql://", "postgres://")):
        raise ValueError("Chuỗi phải bắt đầu bằng postgresql://")
    if "[YOUR-PASSWORD]" in uri:
        password = getpass.getpass("Database password: ")
        uri = uri.replace("[YOUR-PASSWORD]", quote(password, safe=""))
    if "[" in uri or "]" in uri:
        raise ValueError("Connection string vẫn còn phần giữ chỗ [...] chưa được thay")
    return uri


if __name__ == "__main__":
    print("=== SETUP LOCAL TIKTOK ACCOUNT MANAGER ===")
    try:
        if ENV_PATH.exists():
            answer = input("Đã có file .env. Giữ cấu hình hiện tại? [Y/n]: ").strip().lower()
            if answer in {"n", "no"}:
                write_env(collect_database_url())
        else:
            write_env(collect_database_url())
        print("[OK] Đã tạo file .env và SESSION_SECRET ngẫu nhiên.")

        from dotenv import load_dotenv

        load_dotenv(ENV_PATH, override=True)
        from app.database import test_database_connection

        result = test_database_connection()
        if not result["tables_ok"]:
            raise RuntimeError("Thiếu bảng: " + ", ".join(result["missing_tables"]))
        print("[OK] Kết nối Supabase thành công, đủ 5 bảng.")

        from scripts.create_boss import create_boss_interactive

        if not create_boss_interactive():
            raise RuntimeError("Chưa tạo được tài khoản BOSS")
        print("\nHoàn tất. Chạy start.bat hoặc: python server.py")
    except Exception as exc:
        print(f"[X] Setup thất bại: {exc}")
        raise SystemExit(1)

