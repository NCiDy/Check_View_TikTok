-- Mã hóa secret TOTP tại ứng dụng; không lưu mã 6 số.
ALTER TABLE public.tiktok_accounts
  ADD COLUMN IF NOT EXISTS totp_secret_encrypted TEXT;
