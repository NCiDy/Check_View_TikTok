from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

from app.database import test_database_connection  # noqa: E402


if __name__ == "__main__":
    try:
        result = test_database_connection()
        if result["tables_ok"]:
            print("[OK] Kết nối Supabase PostgreSQL thành công và đủ 5 bảng.")
            raise SystemExit(0)
        print("[X] Kết nối được nhưng thiếu bảng:", ", ".join(result["missing_tables"]))
        raise SystemExit(1)
    except Exception as exc:
        print(f"[X] Kết nối database thất bại: {exc}")
        raise SystemExit(1)

