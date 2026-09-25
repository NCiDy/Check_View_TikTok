-- Optional performance indexes only. No rows or video data are removed.
-- Run in Supabase SQL Editor outside an explicit BEGIN/COMMIT block.
-- Existing owner/machine/status indexes are retained; do not duplicate them.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_accounts_machine_followers
ON public.tiktok_accounts (machine_id, followers DESC NULLS LAST, id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_accounts_monetized_followers
ON public.tiktok_accounts (is_monetized DESC, followers DESC NULLS LAST, id);
