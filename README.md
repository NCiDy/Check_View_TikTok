# TikTok Account Manager – Quản lý kênh TikTok

Website quản lý và kiểm tra tài khoản TikTok dành cho công ty BEA Entertaiment, được nâng cấp từ **TikTok Bulk Account Checker Pro**.

Hệ thống sử dụng:

- Python FastAPI.
- HTML, CSS và JavaScript thuần.
- Supabase PostgreSQL để lưu dữ liệu.
- Supabase Storage để lưu ảnh đại diện.
- `curl_cffi` để kiểm tra thông tin TikTok.
- ThreadPoolExecutor để xử lý đồng thời.
- Argon2id để hash mật khẩu.

Dữ liệu không bị mất khi server restart hoặc deploy lại.

---

## Chức năng hiện có

### Đăng nhập và phân quyền

Hệ thống có ba role:

- **BOSS**
  - Xem toàn bộ công ty.
  - Tạo, sửa, khóa và reset mật khẩu Leader/Member.
  - Gán Member cho Leader.
  - Xem và check kênh của từng người.
  - Check một nhóm Leader hoặc toàn công ty.
  - Tìm username TikTok trên toàn hệ thống.
  - Thay ảnh đại diện cho mọi người.
  - Quản lý cấu hình checker và lịch tự động.

- **LEADER**
  - Xem và check kênh của chính mình.
  - Xem Member trực thuộc.
  - Check thủ công từng Member.
  - Không xem được dữ liệu nhóm khác.

- **MEMBER**
  - Chỉ xem dữ liệu của chính mình.
  - Thêm, xóa và check kênh nếu được BOSS cấp quyền.
  - Tự thay ảnh đại diện.

Phân quyền được kiểm tra tại backend, không chỉ ẩn nút trên giao diện.

### Quản lý máy và kênh

- Mỗi người được thêm tối đa 10 máy.
- Mỗi máy chứa tối đa 10 kênh TikTok.
- Mã máy sử dụng số thực tế của công ty, ví dụ `#47`, `#125`.
- Thêm một username hoặc dán nhiều username cùng lúc.
- Hỗ trợ:
  - `@username`
  - `username`
  - `https://www.tiktok.com/@username`
  - `username|password|email|2fa`
- Hệ thống chỉ lấy username, không lưu mật khẩu TikTok, email hoặc 2FA.
- Một username TikTok chỉ thuộc một người trong toàn công ty.
- BOSS có thể chuyển kênh sang người hoặc máy khác.
- Xóa máy sẽ xóa các kênh thuộc máy đó.

### TikTok Checker

Checker hiện hỗ trợ:

- Username và nickname.
- Ảnh đại diện TikTok.
- Bio.
- Followers và following.
- Tổng lượt thích.
- Tổng view mẫu của các video gần đây.
- Trạng thái LIVE, DIE/KHÓA và ERROR.
- Nhận diện tài khoản riêng tư.
- Proxy.
- Retry lỗi mạng.
- Check nhiều tài khoản đồng thời.

Nguyên tắc xác định trạng thái:

- TIMEOUT, HTTP ERROR, PARSE ERROR và lỗi proxy được tính là `ERROR`.
- Không kết luận `DIE` chỉ từ lỗi mạng.
- Kết quả nghi ngờ DIE phải đủ số lần xác nhận.
- Tài khoản riêng tư được xem là LIVE kèm ghi chú “Riêng tư”.
- Không cố lấy video của tài khoản riêng tư.

### Check đồng thời

- Member check kênh của chính mình.
- Leader check bản thân hoặc từng Member.
- BOSS check một người, một nhóm hoặc toàn công ty.
- Mỗi người có job riêng, không phải chờ toàn bộ job khác hoàn thành.
- Toàn hệ thống vẫn bị giới hạn tổng worker để tránh gửi quá nhiều request.
- Nếu cùng một TikTok ID đang được check, hệ thống dùng chung request đang chạy.

### Dashboard

Dashboard hiển thị theo phạm vi quyền:

- Tổng số kênh.
- Tổng LIVE.
- Tổng DIE/KHÓA.
- Tổng ERROR hoặc chưa check.
- Số lỗi mới.
- Lần check gần nhất.
- Tiến độ job đang chạy.
- Lọc danh sách khi bấm vào từng chỉ số.

### So sánh follower

Hệ thống không lưu lịch sử dài hạn.

Mỗi tài khoản chỉ giữ:

- Dữ liệu hiện tại.
- Dữ liệu lần trước.
- Snapshot riêng dành cho lịch tự động.

Khi follower thay đổi đủ ngưỡng, hệ thống có thể hiển thị:

```text
Kênh số 1, máy 47 của Dũng tăng từ 100 lên 300 follow trong khoảng 60 phút
```

### Lịch tự động và đọc loa

BOSS có thể cấu hình:

- Chu kỳ check toàn công ty.
- Ngưỡng thay đổi follower.
- Tổng worker.
- Worker mỗi job.
- Timeout.
- Retry lỗi mạng.
- Số lần xác nhận DIE.
- Delay giữa các request.
- Thông báo trong website.
- Đọc thông báo bằng loa trình duyệt.

Scheduler sử dụng múi giờ:

```text
Asia/Ho_Chi_Minh
```

Để trình duyệt đọc loa:

1. BOSS đăng nhập.
2. Bấm **Bật đọc thông báo** trên Dashboard.
3. Bật **Cho phép đọc loa** trong Cấu hình.
4. Giữ tab website đang mở.

### Ảnh đại diện nhân sự

- Ảnh được lưu trong Supabase Storage.
- Chấp nhận JPG, PNG và WebP.
- Giới hạn tối đa 2 MB.
- BOSS được thay ảnh của mọi người.
- Leader và Member chỉ được thay ảnh của chính mình.
- Nếu chưa có ảnh, hệ thống hiển thị chữ viết tắt của họ tên.

---

## Cấu trúc thư mục

```text
app/
├── config.py          # Đọc biến môi trường
├── database.py        # Kết nối PostgreSQL
├── job_manager.py     # Quản lý job và worker
├── models.py          # SQLAlchemy models
├── permissions.py     # Phân quyền backend
└── security.py        # Session, CSRF và Argon2id

core/
├── checker.py         # TikTok checker
├── proxy_manager.py   # Quản lý proxy
└── worker_pool.py     # Xử lý đa luồng cũ

database/
└── 001_initial_schema.sql

scripts/
├── setup_local.py
├── create_boss.py
└── check_database.py

static/
├── index.html
├── style.css
└── app.js

server.py
start.bat
requirements.txt
.env.example
```

---

## Yêu cầu

- Windows 10 hoặc Windows 11.
- Python 3.11 trở lên.
- Project Supabase Cloud.
- Kết nối Internet.

---

## Thiết lập Supabase

### 1. Tạo database

Trong Supabase:

1. Tạo project.
2. Mở **SQL Editor**.
3. Chạy file:

```text
database/001_initial_schema.sql
```

Database gồm năm bảng:

- `users`
- `machines`
- `tiktok_accounts`
- `check_runs`
- `app_settings`

### 2. Cập nhật mã máy và ảnh đại diện

Nếu database được tạo từ schema cũ, chạy thêm:

```sql
ALTER TABLE public.machines
DROP CONSTRAINT IF EXISTS machines_machine_number_check;

ALTER TABLE public.machines
ADD CONSTRAINT machines_machine_number_check
CHECK (machine_number BETWEEN 1 AND 32767);

ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS avatar_url text;
```

### 3. Tạo Storage bucket

Trong Supabase:

1. Mở **Storage**.
2. Chọn **New bucket**.
3. Đặt tên:

```text
avatars
```

4. Bật **Public bucket**.
5. Tạo bucket.

---

## Cấu hình `.env`

Sao chép `.env.example` thành `.env` hoặc chạy `start.bat`.

Ví dụ:

```env
DATABASE_URL="postgresql://postgres.PROJECT_REF:DATABASE_PASSWORD@HOST:5432/postgres"

SESSION_SECRET="chuoi-ngau-nhien-dai-va-kho-doan"

APP_ENV="development"
COOKIE_SECURE="false"

SUPABASE_URL="https://PROJECT_REF.supabase.co"
SUPABASE_SERVICE_ROLE_KEY="SUPABASE_SERVICE_ROLE_KEY"

PROXY_MODE="direct"
PROXY_LIST=""
ROTATING_PROXY_URL=""
```

Trong đó:

- `DATABASE_URL`: URI Session pooler cổng 5432 của Supabase.
- `SESSION_SECRET`: chuỗi ngẫu nhiên dùng để bảo vệ session.
- `SUPABASE_URL`: Project URL, không chứa `/rest/v1/`.
- `SUPABASE_SERVICE_ROLE_KEY`: dùng để upload ảnh lên Storage.
- `PROXY_MODE=direct`: kết nối trực tiếp, chưa sử dụng proxy.

Không commit `.env` lên GitHub.

`SUPABASE_SERVICE_ROLE_KEY` có quyền rất cao và tuyệt đối không được đặt trong JavaScript hoặc HTML.

---

## Chạy trên Windows

### Cách đơn giản

Nhấp đúp:

```text
start.bat
```

Lần chạy đầu chương trình sẽ:

1. Kiểm tra Python.
2. Cài thư viện.
3. Tạo `.env` nếu chưa có.
4. Kiểm tra kết nối Supabase.
5. Hướng dẫn tạo BOSS.
6. Chạy FastAPI.

Mở trình duyệt tại:

```text
http://127.0.0.1:8088
```

### Chạy bằng VS Code

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\setup_local.py
python scripts\check_database.py
python server.py
```

---

## Tạo tài khoản BOSS

Nếu database chưa có BOSS:

```powershell
python scripts\create_boss.py
```

Mật khẩu được hash bằng Argon2id trước khi lưu. Hệ thống không lưu mật khẩu gốc.

BOSS có thể tạo thêm Leader và Member trong giao diện **Quản lý nhân sự**.

---

## Cấu hình checker đề xuất

Với công ty khoảng 14 người và vài trăm kênh:

```text
Chu kỳ tự động:        60 phút
Ngưỡng follow:         100
Tổng worker:           10
Worker mỗi job:        3
Timeout:               12 giây
Retry lỗi mạng:        2
Xác nhận DIE:          2
Delay request:         0,3 giây
```

Không nên tăng worker quá cao khi chưa có proxy ổn định.

---

## Kiểm thử cơ bản

### BOSS

- Đăng nhập thành công.
- Tạo Leader.
- Tạo Member và gán đúng Leader.
- Reset mật khẩu.
- Thêm máy bằng mã thực tế như `#47`.
- Thêm kênh TikTok.
- Check một người.
- Check toàn công ty.
- Tìm username toàn hệ thống.
- Thay ảnh đại diện.
- Bật lịch và đọc loa.

### Leader

- Chỉ thấy bản thân và Member trực thuộc.
- Không thấy nhóm Leader khác.
- Check được bản thân.
- Check được từng Member.
- Không truy cập chức năng dành riêng cho BOSS.

### Member

- Chỉ thấy dữ liệu chính mình.
- Thêm, xóa và check theo quyền BOSS đã cấp.
- Không xem được dữ liệu người khác.
- Chỉ thay được ảnh đại diện của chính mình.

### Kiểm tra dữ liệu

- Nhấn `F5`, máy, kênh và kết quả check vẫn còn.
- Restart server, dữ liệu vẫn còn.
- BOSS check kênh của Member thì Member nhìn thấy kết quả mới.
- Cùng một TikTok ID không tạo dữ liệu riêng theo người check.
- Timeout và lỗi mạng phải là ERROR, không phải DIE.

---

## Chạy test kỹ thuật

```powershell
python -m pip install -r requirements-dev.txt
python -m compileall app core server.py scripts
python -m pytest -q
```

---

## Bảo mật

- Không commit `.env`.
- Không đưa database password hoặc service role key vào source code.
- Mật khẩu đăng nhập được hash bằng Argon2id.
- API thay đổi dữ liệu được bảo vệ bằng session và CSRF.
- Phân quyền được kiểm tra tại backend.
- Cookie production phải bật `Secure`.
- API checker không được sử dụng khi chưa đăng nhập.
- Nên đổi mật khẩu BOSS sau lần setup đầu tiên.
- Không gửi ảnh chụp có mật khẩu hoặc secret trên màn hình.

---

## Deploy

Khi deploy cần thiết lập:

```env
DATABASE_URL="..."
SESSION_SECRET="..."
APP_ENV="production"
COOKIE_SECURE="true"
SUPABASE_URL="..."
SUPABASE_SERVICE_ROLE_KEY="..."
```

Start command:

```text
python server.py
```

Ứng dụng tự đọc biến `PORT` do nền tảng deploy cung cấp.

Lưu ý:

- Không sử dụng SQLite trên filesystem tạm.
- Supabase PostgreSQL và Storage giữ dữ liệu sau khi deploy lại.
- Scheduler hiện chạy cùng tiến trình FastAPI.
- Nếu hosting miễn phí chuyển sang trạng thái ngủ, lịch tự động sẽ không chạy trong thời gian server ngủ.
- Bản demo chỉ nên chạy một instance FastAPI để tránh nhiều scheduler chạy trùng.

---

## Chức năng chưa triển khai

- Xuất Excel, CSV và TXT trên giao diện mới.
- Biểu đồ lịch sử dài hạn.
- Ứng dụng mobile.
- Hệ thống hàng đợi Redis/Celery.
- Gửi thông báo qua Zalo, Telegram hoặc email.

Những chức năng này được tạm hoãn để giữ hệ thống đơn giản, dễ sử dụng và dễ bảo trì.
