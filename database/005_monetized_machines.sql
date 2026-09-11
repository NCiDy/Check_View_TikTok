BEGIN;

ALTER TABLE public.machines
    ADD COLUMN IF NOT EXISTS machine_type text NOT NULL DEFAULT 'NORMAL';

ALTER TABLE public.machines
    DROP CONSTRAINT IF EXISTS machines_machine_type_check;

ALTER TABLE public.machines
    ADD CONSTRAINT machines_machine_type_check
    CHECK (machine_type IN ('NORMAL', 'MONETIZED'));

ALTER TABLE public.tiktok_accounts
    ADD COLUMN IF NOT EXISTS is_monetized boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS monetized_at timestamptz NULL;

ALTER TABLE public.tiktok_accounts
    DROP CONSTRAINT IF EXISTS tiktok_accounts_monetized_at_check;

ALTER TABLE public.tiktok_accounts
    ADD CONSTRAINT tiktok_accounts_monetized_at_check
    CHECK (is_monetized OR monetized_at IS NULL);

ALTER TABLE public.app_settings
    ADD COLUMN IF NOT EXISTS monetization_follower_threshold bigint NOT NULL DEFAULT 10500;

ALTER TABLE public.app_settings
    DROP CONSTRAINT IF EXISTS app_settings_monetization_threshold_check;

ALTER TABLE public.app_settings
    ADD CONSTRAINT app_settings_monetization_threshold_check
    CHECK (monetization_follower_threshold BETWEEN 1 AND 1000000000);

CREATE INDEX IF NOT EXISTS ix_machines_owner_type_number
    ON public.machines(owner_id, machine_type, machine_number);

CREATE INDEX IF NOT EXISTS ix_tiktok_accounts_is_monetized
    ON public.tiktok_accounts(is_monetized);

COMMIT;


BEGIN;

-- Cho phép cùng số máy giữa hai loại NORMAL và MONETIZED.
ALTER TABLE public.machines
    DROP CONSTRAINT IF EXISTS machines_owner_number_unique;

ALTER TABLE public.machines
    DROP CONSTRAINT IF EXISTS machines_owner_type_number_unique;

ALTER TABLE public.machines
    ADD CONSTRAINT machines_owner_type_number_unique
    UNIQUE (owner_id, machine_type, machine_number);

COMMIT;