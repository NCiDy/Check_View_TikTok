-- Thiết lập giới hạn giờ dùng 2FA cho MEMBER/LEADER.
ALTER TABLE public.app_settings
  ADD COLUMN IF NOT EXISTS totp_time_restriction_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS totp_restricted_roles TEXT NOT NULL DEFAULT 'MEMBER',
  ADD COLUMN IF NOT EXISTS totp_access_start_minutes SMALLINT NOT NULL DEFAULT 480,
  ADD COLUMN IF NOT EXISTS totp_access_end_minutes SMALLINT NOT NULL DEFAULT 1080;
