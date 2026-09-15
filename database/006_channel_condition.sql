BEGIN;

ALTER TABLE public.tiktok_accounts
    ADD COLUMN IF NOT EXISTS channel_condition text NULL;

ALTER TABLE public.tiktok_accounts
    DROP CONSTRAINT IF EXISTS tiktok_accounts_channel_condition_check;

ALTER TABLE public.tiktok_accounts
    ADD CONSTRAINT tiktok_accounts_channel_condition_check
    CHECK (
        channel_condition IS NULL OR channel_condition IN (
            'ONE_STRIKE',
            'TWO_STRIKES',
            'THREE_STRIKES',
            'FOUR_STRIKES',
            'OUT_BETA_REVIEW',
            'REJECTED'
        )
    );

CREATE INDEX IF NOT EXISTS ix_tiktok_accounts_channel_condition
    ON public.tiktok_accounts(channel_condition)
    WHERE channel_condition IS NOT NULL;

COMMIT;

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS max_active_sessions smallint NOT NULL DEFAULT 1;

ALTER TABLE public.users
    DROP CONSTRAINT IF EXISTS users_max_active_sessions_check;

ALTER TABLE public.users
    ADD CONSTRAINT users_max_active_sessions_check
    CHECK (max_active_sessions BETWEEN 1 AND 5);

UPDATE public.users
SET max_active_sessions = CASE
    WHEN username_normalized IN ('admin', 'system') THEN 2
    ELSE 1
END;

DROP INDEX IF EXISTS public.ux_user_sessions_one_active_per_user;

CREATE INDEX IF NOT EXISTS ix_user_sessions_active_user
    ON public.user_sessions(user_id, created_at DESC)
    WHERE revoked_at IS NULL;
