-- Enterprise session isolation, multiple BOSS accounts and compact audit log.
-- Run once in Supabase SQL Editor after 001_initial_schema.sql.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- User administration
-- ---------------------------------------------------------------------------

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS is_system_owner boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS show_in_org_chart boolean NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS avatar_url text NULL;

DROP INDEX IF EXISTS public.ux_users_single_active_boss;

-- Promote the oldest active BOSS as the technical owner when upgrading.
UPDATE public.users
SET is_system_owner = true
WHERE id = (
    SELECT id
    FROM public.users
    WHERE role = 'BOSS' AND is_active = true
    ORDER BY created_at, id
    LIMIT 1
)
AND NOT EXISTS (
    SELECT 1 FROM public.users WHERE is_system_owner = true
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_one_system_owner
    ON public.users ((is_system_owner))
    WHERE is_system_owner = true;

ALTER TABLE public.users
    DROP CONSTRAINT IF EXISTS users_system_owner_must_be_boss;

ALTER TABLE public.users
    ADD CONSTRAINT users_system_owner_must_be_boss
    CHECK (NOT is_system_owner OR (role = 'BOSS' AND is_active = true));

CREATE OR REPLACE FUNCTION public.enforce_active_boss_limit()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    active_count integer;
BEGIN
    -- Serialize BOSS count changes so two simultaneous creates cannot exceed 3.
    PERFORM pg_advisory_xact_lock(hashtext('public.users.active_boss_limit'));

    IF NEW.role = 'BOSS' AND NEW.is_active = true THEN
        SELECT count(*) INTO active_count
        FROM public.users
        WHERE role = 'BOSS'
          AND is_active = true
          AND id <> NEW.id;

        IF active_count >= 3 THEN
            RAISE EXCEPTION 'Tối đa 3 tài khoản BOSS đang hoạt động';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_users_active_boss_limit ON public.users;
CREATE TRIGGER trg_users_active_boss_limit
BEFORE INSERT OR UPDATE OF role, is_active ON public.users
FOR EACH ROW EXECUTE FUNCTION public.enforce_active_boss_limit();

-- Machine labels are company asset numbers, not positions 1..10.
ALTER TABLE public.machines
    DROP CONSTRAINT IF EXISTS machines_machine_number_check;
ALTER TABLE public.machines
    ADD CONSTRAINT machines_machine_number_check
    CHECK (machine_number BETWEEN 1 AND 32767);

-- ---------------------------------------------------------------------------
-- Database-backed login sessions. One active device per login account.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.user_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    ip_address text NULL,
    user_agent text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz NULL,
    revoked_reason text NULL,
    CONSTRAINT user_sessions_expiry_after_create CHECK (expires_at > created_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_user_sessions_one_active_per_user
    ON public.user_sessions(user_id)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_user_sessions_active_expiry
    ON public.user_sessions(expires_at)
    WHERE revoked_at IS NULL;

-- ---------------------------------------------------------------------------
-- Bind manual job progress to the browser session that started it.
-- ---------------------------------------------------------------------------

ALTER TABLE public.check_runs
    ADD COLUMN IF NOT EXISTS requested_session_id uuid NULL
        REFERENCES public.user_sessions(id) ON DELETE SET NULL;

DROP INDEX IF EXISTS public.ux_check_runs_one_active_per_user;

CREATE UNIQUE INDEX IF NOT EXISTS ux_check_runs_one_active_per_session
    ON public.check_runs(requested_session_id)
    WHERE requested_session_id IS NOT NULL
      AND trigger_type = 'MANUAL'
      AND status IN ('QUEUED', 'RUNNING');

CREATE INDEX IF NOT EXISTS ix_check_runs_session_created
    ON public.check_runs(requested_session_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Compact audit log. It records actions, never passwords or secrets.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.audit_logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_user_id uuid NULL REFERENCES public.users(id) ON DELETE SET NULL,
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id text NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    ip_address text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT audit_logs_action_not_blank CHECK (char_length(btrim(action)) BETWEEN 1 AND 100),
    CONSTRAINT audit_logs_entity_type_not_blank CHECK (char_length(btrim(entity_type)) BETWEEN 1 AND 50)
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at
    ON public.audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_created
    ON public.audit_logs(actor_user_id, created_at DESC);

ALTER TABLE public.user_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

COMMIT;
