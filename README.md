# TikTok Account Manager – bản nội bộ công ty

Bản nâng cấp từ **TikTok Bulk Account Checker Pro**. Checker `curl_cffi`, hỗ trợ
proxy và xử lý nhiều luồng được giữ lại; dữ liệu, đăng nhập và phân quyền đã
chuyển sang Supabase PostgreSQL.

## Chức năng hiện có

- Đăng nhập bằng session cookie; mật khẩu lưu Argon2id.
- Role BOSS, LEADER, MEMBER và kiểm tra quyền ở backend.
- BOSS tạo/khóa/reset mật khẩu Leader, Member; gán Member cho Leader.
- Mỗi người tối đa 10 máy, mỗi máy tối đa 10 kênh.
- Thêm một hoặc dán hàng loạt username theo định dạng tool cũ.
- Một username chỉ thuộc một người trong toàn công ty.
- BOSS chuyển kênh sang người/máy khác.
- Dashboard theo phạm vi role; lọc LIVE, DIE, ERROR và chưa check.
- Check kênh đã chọn, một người, nhóm Leader (BOSS) hoặc toàn công ty (BOSS).
- Leader chỉ check bản thân hoặc từng Member trực thuộc; không check cả nhóm.
- Nhiều người chạy job độc lập; cùng TikTok ID thì dùng chung request đang chạy.
- Retry TIMEOUT/HTTP/PARSE; các lỗi này không được kết luận DIE.
- TikTok 404 cần đủ số lần xác nhận trước khi chuyển DIE.
- PRIVATE hiển thị LIVE + ghi chú Riêng tư và không xử lý video.
- Lưu current/previous followers và snapshot riêng cho lịch tự động.
- Lịch check toàn công ty theo phút, mặc định 60 phút.
- Thông báo trong web và đọc loa trình duyệt khi tab của BOSS đang mở.
- Tìm username toàn công ty chỉ dành cho BOSS.

Xuất Excel/CSV/TXT được tạm hoãn theo yêu cầu và chưa xuất hiện trong giao diện.

## Chạy lần đầu trên Windows

1. Đảm bảo đã chạy `database/001_initial_schema.sql` trong Supabase SQL Editor.
2. Nhấp đúp `start.bat`.
   Nếu Python Portable cũ thiếu `python311.zip`, file này sẽ tự tải lại runtime
   Python 3.11 Embedded chính thức rồi mới cài thư viện.
3. Lần đầu, chương trình yêu cầu dán URI **Session pooler cổng 5432**.
4. Nếu URI còn `[YOUR-PASSWORD]`, nhập Database password khi được hỏi.
5. Tạo username, họ tên và mật khẩu BOSS.
6. Trình duyệt mở `http://127.0.0.1:8088`.

Chuỗi kết nối và mật khẩu thật chỉ nằm trong `.env`; `.gitignore` đã chặn file này.

## Chạy bằng VS Code/Terminal

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\setup_local.py
python scripts\check_database.py
python server.py
```

## Tạo BOSS riêng

Nếu `.env` đã có nhưng chưa có BOSS:

```powershell
python scripts\create_boss.py
```

## Biến môi trường deploy

Xem `.env.example`. Khi deploy cần tối thiểu:

- `DATABASE_URL`: URI Supabase Session pooler 5432.
- `SESSION_SECRET`: chuỗi ngẫu nhiên dài.
- `APP_ENV=production`.
- `COOKIE_SECURE=true`.
- `PORT`: do nền tảng deploy cung cấp.

Không đặt secret trực tiếp trong source code hoặc commit `.env` lên GitHub.

## Lưu ý scheduler và loa

- Scheduler chạy trong tiến trình FastAPI, phù hợp bản demo một server.
- Nếu hosting miễn phí ngủ, lịch không thể chạy khi server đang ngủ.
- Loa dùng Web Speech API; người dùng phải bấm **Bật đọc thông báo** ít nhất một
  lần và giữ tab trình duyệt mở.

## Kiểm tra nhanh

```powershell
python -m pip install -r requirements-dev.txt
python -m compileall app core server.py scripts
python -m pytest -q
```
