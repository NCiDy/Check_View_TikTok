BEGIN;

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS is_technical_account boolean
    NOT NULL DEFAULT false;

ALTER TABLE public.users
    DROP CONSTRAINT IF EXISTS users_technical_account_shape;

ALTER TABLE public.users
    ADD CONSTRAINT users_technical_account_shape
    CHECK (
        NOT is_technical_account
        OR (
            role = 'BOSS'
            AND is_active = true
            AND is_system_owner = false
            AND show_in_org_chart = false
        )
    );

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_one_technical_account
    ON public.users ((is_technical_account))
    WHERE is_technical_account = true;

-- Tài khoản kỹ thuật không chiếm giới hạn 3 BOSS nghiệp vụ.
CREATE OR REPLACE FUNCTION public.enforce_active_boss_limit()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    active_count integer;
BEGIN
    PERFORM pg_advisory_xact_lock(
        hashtext('public.users.active_boss_limit')
    );

    IF NEW.role = 'BOSS'
       AND NEW.is_active = true
       AND NEW.is_technical_account = false
    THEN
        SELECT count(*)
        INTO active_count
        FROM public.users
        WHERE role = 'BOSS'
          AND is_active = true
          AND is_technical_account = false
          AND id <> NEW.id;

        IF active_count >= 3 THEN
            RAISE EXCEPTION
                'Tối đa 3 tài khoản BOSS đang hoạt động';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_users_active_boss_limit
ON public.users;

CREATE TRIGGER trg_users_active_boss_limit
BEFORE INSERT OR UPDATE OF
    role,
    is_active,
    is_technical_account
ON public.users
FOR EACH ROW
EXECUTE FUNCTION public.enforce_active_boss_limit();

COMMIT;