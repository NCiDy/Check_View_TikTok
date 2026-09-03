# Nâng cấp database lên schema v4

Migration này giữ nguyên toàn bộ `users`, máy, kênh TikTok và kết quả hiện tại.
Không chạy lại `001_initial_schema.sql` trên project đang sử dụng.

## 1. Sao lưu nhanh

Trong Supabase, mở **Table Editor** và export CSV các bảng quan trọng:

- `users`
- `machines`
- `tiktok_accounts`
- `check_runs`
- `app_settings`

Không chỉnh sửa dữ liệu trong lúc chạy migration.

## 2. Chạy migration

1. Mở Supabase → **SQL Editor**.
2. Chọn **New query**.
3. Sao chép toàn bộ nội dung `002_enterprise_sessions.sql`.
4. Nhấn **Run** đúng một lần.

File có transaction và các câu lệnh `IF EXISTS/IF NOT EXISTS`, vì vậy có thể chạy
lại nếu lần đầu bị ngắt trước khi hoàn tất.

## 3. Kiểm tra kết quả

Chạy truy vấn:

```sql
select table_name
from information_schema.tables
where table_schema = 'public'
  and table_name in ('user_sessions', 'audit_logs');

select username, role, is_system_owner, is_active
from public.users
where role = 'BOSS'
order by created_at;
```

Kết quả cần có:

- Hai bảng `user_sessions`, `audit_logs`.
- Tài khoản BOSS cũ có `is_system_owner = true`.

## 4. Tạo hai BOSS thử nghiệm

Sau khi chạy code v4:

1. Đăng nhập tài khoản `admin`.
2. Mở **Quản lý nhân sự** → **Thêm nhân sự**.
3. Chọn role `BOSS`.
4. Tạo từng tài khoản thử nghiệm.
5. Bỏ chọn **Hiện trong sơ đồ** nếu đây chỉ là tài khoản test của Leader.

Mật khẩu được FastAPI hash bằng Argon2id. Không tạo BOSS bằng cách ghi mật khẩu
gốc trực tiếp trong SQL.

## 5. Cập nhật Render

Build command:

```text
bash render-build.sh
```

Start command:

```text
python server.py
```

Giữ nguyên các biến môi trường hiện tại. Nếu đã đổi database password, cập nhật
`DATABASE_URL` ở cả Render và file `.env` trên máy local.

## 6. Quay lại nếu deployment lỗi

Giao diện cũ vẫn có tại `/legacy`. Không xóa migration hoặc các cột mới. Nếu cần,
rollback deployment code về commit trước; dữ liệu cũ vẫn tương thích và không bị
migration này xóa.
