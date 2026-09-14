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
