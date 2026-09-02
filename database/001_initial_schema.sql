-- TikTok Bulk Account Checker Pro
-- Initial schema for Supabase PostgreSQL
--
-- Final first-version design:
--   1. users            : BOSS / LEADER / MEMBER and per-user permissions.
--   2. machines         : numbered machines belonging to a user (maximum 10).
--   3. tiktok_accounts  : one shared row per TikTok username, maximum 10 per machine.
--   4. check_runs       : independent manual/scheduled jobs and their progress.
--   5. app_settings     : singleton scheduler/checker configuration.
--
-- Important rules:
--   * A TikTok username belongs to exactly one machine/user company-wide.
--   * Whoever checks an account (BOSS, LEADER, MEMBER, scheduler) updates the
--     same tiktok_accounts row. Data is never duplicated by role.
--   * Only current/previous values are retained; there is no long-term history.
--   * Manual checks update the latest snapshot. Scheduled checks additionally
--     rotate a separate bounded auto snapshot so hourly comparisons stay valid.
--   * TikTok passwords, emails, 2FA secrets and proxy credentials are never stored.
--   * Application passwords are Argon2id hashes generated/verified by FastAPI.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Shared trigger: maintain updated_at automatically.
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- users
-- Internal login accounts. FastAPI owns authentication and role authorization.
-- Password changes are optional; BOSS can reset by replacing password_hash.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    username text NOT NULL,
    username_normalized text
        GENERATED ALWAYS AS (lower(btrim(username))) STORED,
    password_hash text NOT NULL,
    full_name text NOT NULL,

    role text NOT NULL
        CHECK (role IN ('BOSS', 'LEADER', 'MEMBER')),
    leader_id uuid NULL
        REFERENCES public.users(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    -- BOSS always has full access through backend role rules.
    -- LEADER/MEMBER can manage only their own list when BOSS enables these.
    can_add_accounts boolean NOT NULL DEFAULT false,
    can_delete_accounts boolean NOT NULL DEFAULT false,
    can_run_checks boolean NOT NULL DEFAULT true,

    is_active boolean NOT NULL DEFAULT true,
    last_login_at timestamptz NULL,
    password_changed_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT users_username_not_blank
        CHECK (char_length(btrim(username)) BETWEEN 3 AND 100),
    CONSTRAINT users_full_name_not_blank
        CHECK (char_length(btrim(full_name)) BETWEEN 1 AND 150),
    CONSTRAINT users_password_hash_not_blank
        CHECK (char_length(btrim(password_hash)) >= 20),
    CONSTRAINT users_leader_shape
        CHECK (
            (role = 'MEMBER' AND leader_id IS NOT NULL)
            OR
            (role IN ('BOSS', 'LEADER') AND leader_id IS NULL)
        ),
    CONSTRAINT users_cannot_lead_self
        CHECK (leader_id IS NULL OR leader_id <> id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username_normalized
    ON public.users(username_normalized);

-- Keep one active BOSS for the simple first version.
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_single_active_boss
    ON public.users ((role))
    WHERE role = 'BOSS' AND is_active = true;

CREATE INDEX IF NOT EXISTS ix_users_leader_id
    ON public.users(leader_id)
    WHERE leader_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_users_role_active
    ON public.users(role, is_active);

CREATE OR REPLACE FUNCTION public.validate_user_hierarchy()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    assigned_leader_role text;
    assigned_leader_active boolean;
BEGIN
    IF NEW.role = 'MEMBER' THEN
        IF NEW.leader_id IS NULL THEN
            RAISE EXCEPTION 'MEMBER must belong to a LEADER';
        END IF;

        SELECT role, is_active
          INTO assigned_leader_role, assigned_leader_active
          FROM public.users
         WHERE id = NEW.leader_id;

        IF assigned_leader_role IS DISTINCT FROM 'LEADER'
           OR assigned_leader_active IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'leader_id must reference an active LEADER account';
        END IF;
    ELSIF NEW.leader_id IS NOT NULL THEN
        RAISE EXCEPTION 'Only MEMBER accounts may have leader_id';
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF OLD.role = 'LEADER'
           AND (
               NEW.role <> 'LEADER'
               OR (OLD.is_active = true AND NEW.is_active = false)
           )
           AND EXISTS (
               SELECT 1
                 FROM public.users member_user
                WHERE member_user.leader_id = OLD.id
                  AND member_user.is_active = true
           ) THEN
            RAISE EXCEPTION
                'Reassign or deactivate this Leader''s active Members first';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_users_validate_hierarchy ON public.users;
CREATE TRIGGER trg_users_validate_hierarchy
BEFORE INSERT OR UPDATE OF role, leader_id, is_active
ON public.users
FOR EACH ROW
EXECUTE FUNCTION public.validate_user_hierarchy();

DROP TRIGGER IF EXISTS trg_users_set_updated_at ON public.users;
CREATE TRIGGER trg_users_set_updated_at
BEFORE UPDATE ON public.users
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- machines
-- Each user can have machine numbers 1..10. Number is unique per user.
-- Deleting a machine intentionally deletes its TikTok rows through CASCADE.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.machines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL
        REFERENCES public.users(id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    machine_number smallint NOT NULL
        CHECK (machine_number BETWEEN 1 AND 10),
    note text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT machines_owner_number_unique
        UNIQUE (owner_id, machine_number),
    CONSTRAINT machines_note_length
        CHECK (note IS NULL OR char_length(note) <= 200)
);

CREATE INDEX IF NOT EXISTS ix_machines_owner_id
    ON public.machines(owner_id, machine_number);

DROP TRIGGER IF EXISTS trg_machines_set_updated_at ON public.machines;
CREATE TRIGGER trg_machines_set_updated_at
BEFORE UPDATE ON public.machines
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- tiktok_accounts
-- One bounded/shared row per TikTok username. Ownership is derived through:
-- tiktok_accounts.machine_id -> machines.owner_id -> users.id.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.tiktok_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    machine_id uuid NOT NULL
        REFERENCES public.machines(id)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    slot_number smallint NOT NULL
        CHECK (slot_number BETWEEN 1 AND 10),

    username text NOT NULL,
    username_normalized text
        GENERATED ALWAYS AS (
            lower(trim(leading '@' FROM btrim(username)))
        ) STORED,

    nickname text NULL,
    avatar_url text NULL,
    bio text NULL,

    -- Latest valid metrics from any authorized checker.
    followers bigint NULL,
    previous_followers bigint NULL,
    following bigint NULL,
    total_likes bigint NULL,

    -- Recent public sample only, not guaranteed lifetime account views.
    total_sample_views bigint NULL,
    avg_sample_views bigint NULL,
    video_count_sample integer NOT NULL DEFAULT 0,
    recent_videos jsonb NOT NULL DEFAULT '[]'::jsonb,

    -- Latest state from any authorized checker.
    status text NOT NULL DEFAULT 'UNCHECKED'
        CHECK (status IN ('UNCHECKED', 'LIVE', 'DIE', 'ERROR')),
    previous_status text NULL
        CHECK (
            previous_status IS NULL
            OR previous_status IN ('UNCHECKED', 'LIVE', 'DIE', 'ERROR')
        ),
    is_private boolean NOT NULL DEFAULT false,
    is_verified boolean NOT NULL DEFAULT false,

    last_error_code text NULL,
    last_error_message text NULL,
    last_http_status integer NULL,
    dead_confirmation_count smallint NOT NULL DEFAULT 0
        CHECK (dead_confirmation_count BETWEEN 0 AND 10),

    -- Any check attempt, including ERROR.
    last_checked_at timestamptz NULL,
    previous_checked_at timestamptz NULL,
    last_checked_by uuid NULL
        REFERENCES public.users(id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,

    -- Only a successful response rotates follower metrics and these times.
    last_successful_checked_at timestamptz NULL,
    previous_successful_checked_at timestamptz NULL,

    -- Bounded scheduled snapshots. Manual checks do not rotate these fields.
    -- This preserves an accurate interval when users check between auto runs.
    auto_followers bigint NULL,
    previous_auto_followers bigint NULL,
    auto_status text NULL
        CHECK (
            auto_status IS NULL
            OR auto_status IN ('UNCHECKED', 'LIVE', 'DIE', 'ERROR')
        ),
    previous_auto_status text NULL
        CHECK (
            previous_auto_status IS NULL
            OR previous_auto_status IN ('UNCHECKED', 'LIVE', 'DIE', 'ERROR')
        ),
    auto_checked_at timestamptz NULL,
    previous_auto_checked_at timestamptz NULL,
    auto_successful_checked_at timestamptz NULL,
    previous_auto_successful_checked_at timestamptz NULL,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT tiktok_accounts_machine_slot_unique
        UNIQUE (machine_id, slot_number),
    CONSTRAINT tiktok_accounts_username_not_blank
        CHECK (char_length(username_normalized) BETWEEN 1 AND 100),
    CONSTRAINT tiktok_accounts_followers_nonnegative
        CHECK (followers IS NULL OR followers >= 0),
    CONSTRAINT tiktok_accounts_previous_followers_nonnegative
        CHECK (previous_followers IS NULL OR previous_followers >= 0),
    CONSTRAINT tiktok_accounts_following_nonnegative
        CHECK (following IS NULL OR following >= 0),
    CONSTRAINT tiktok_accounts_total_likes_nonnegative
        CHECK (total_likes IS NULL OR total_likes >= 0),
    CONSTRAINT tiktok_accounts_total_sample_views_nonnegative
        CHECK (total_sample_views IS NULL OR total_sample_views >= 0),
    CONSTRAINT tiktok_accounts_avg_sample_views_nonnegative
        CHECK (avg_sample_views IS NULL OR avg_sample_views >= 0),
    CONSTRAINT tiktok_accounts_video_count_nonnegative
        CHECK (video_count_sample >= 0),
    CONSTRAINT tiktok_accounts_recent_videos_is_array
        CHECK (jsonb_typeof(recent_videos) = 'array'),
    CONSTRAINT tiktok_accounts_private_not_dead
        CHECK (is_private = false OR status IN ('LIVE', 'ERROR')),
    CONSTRAINT tiktok_accounts_check_time_order
        CHECK (
            previous_checked_at IS NULL
            OR last_checked_at IS NULL
            OR previous_checked_at <= last_checked_at
        ),
    CONSTRAINT tiktok_accounts_success_time_order
        CHECK (
            previous_successful_checked_at IS NULL
            OR last_successful_checked_at IS NULL
            OR previous_successful_checked_at <= last_successful_checked_at
        ),
    CONSTRAINT tiktok_accounts_auto_time_order
        CHECK (
            previous_auto_checked_at IS NULL
            OR auto_checked_at IS NULL
            OR previous_auto_checked_at <= auto_checked_at
        ),
    CONSTRAINT tiktok_accounts_auto_success_time_order
        CHECK (
            previous_auto_successful_checked_at IS NULL
            OR auto_successful_checked_at IS NULL
            OR previous_auto_successful_checked_at <= auto_successful_checked_at
        )
);

-- A TikTok username can belong to only one machine/person company-wide.
CREATE UNIQUE INDEX IF NOT EXISTS ux_tiktok_accounts_username_normalized
    ON public.tiktok_accounts(username_normalized);

CREATE INDEX IF NOT EXISTS ix_tiktok_accounts_machine_slot
    ON public.tiktok_accounts(machine_id, slot_number);

CREATE INDEX IF NOT EXISTS ix_tiktok_accounts_machine_status
    ON public.tiktok_accounts(machine_id, status);

CREATE INDEX IF NOT EXISTS ix_tiktok_accounts_status
    ON public.tiktok_accounts(status);

CREATE INDEX IF NOT EXISTS ix_tiktok_accounts_last_checked_at
    ON public.tiktok_accounts(last_checked_at DESC NULLS LAST);

DROP TRIGGER IF EXISTS trg_tiktok_accounts_set_updated_at
    ON public.tiktok_accounts;
CREATE TRIGGER trg_tiktok_accounts_set_updated_at
BEFORE UPDATE ON public.tiktok_accounts
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- check_runs
-- Different users can have independent jobs at the same time. FastAPI applies
-- a shared worker limit and deduplicates an in-flight TikTok username so two
-- overlapping jobs reuse one request/result.
--
-- Backend authorization:
--   MEMBER -> USER for self, or SELECTED from self.
--   LEADER -> USER for self/direct Member, or SELECTED in that person's list.
--             LEADER cannot start LEADER_GROUP or COMPANY.
--   BOSS   -> every scope, including LEADER_GROUP and COMPANY.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.check_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    requested_by uuid NULL
        REFERENCES public.users(id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    trigger_type text NOT NULL
        CHECK (trigger_type IN ('MANUAL', 'SCHEDULED')),
    scope_type text NOT NULL
        CHECK (
            scope_type IN (
                'SELECTED',
                'USER',
                'LEADER_GROUP',
                'COMPANY'
            )
        ),
    target_user_id uuid NULL
        REFERENCES public.users(id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,

    -- Present only for SELECTED. Old completed runs are cleaned by FastAPI.
    selected_account_ids uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],

    status text NOT NULL DEFAULT 'QUEUED'
        CHECK (
            status IN (
                'QUEUED',
                'RUNNING',
                'COMPLETED',
                'STOPPED',
                'FAILED'
            )
        ),
    priority smallint NOT NULL DEFAULT 10
        CHECK (priority BETWEEN 0 AND 100),

    total_accounts integer NOT NULL DEFAULT 0,
    processed_accounts integer NOT NULL DEFAULT 0,
    live_count integer NOT NULL DEFAULT 0,
    die_count integer NOT NULL DEFAULT 0,
    error_count integer NOT NULL DEFAULT 0,
    follower_changed_count integer NOT NULL DEFAULT 0,
    new_problem_count integer NOT NULL DEFAULT 0,

    message text NULL,
    started_at timestamptz NULL,
    finished_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT check_runs_counts_nonnegative
        CHECK (
            total_accounts >= 0
            AND processed_accounts >= 0
            AND live_count >= 0
            AND die_count >= 0
            AND error_count >= 0
            AND follower_changed_count >= 0
            AND new_problem_count >= 0
        ),
    CONSTRAINT check_runs_processed_not_above_total
        CHECK (processed_accounts <= total_accounts),
    CONSTRAINT check_runs_finished_after_started
        CHECK (
            finished_at IS NULL
            OR started_at IS NULL
            OR finished_at >= started_at
        ),
    CONSTRAINT check_runs_selected_scope_shape
        CHECK (
            (scope_type = 'SELECTED' AND cardinality(selected_account_ids) > 0)
            OR
            (scope_type <> 'SELECTED' AND cardinality(selected_account_ids) = 0)
        ),
    CONSTRAINT check_runs_target_scope_shape
        CHECK (
            (scope_type IN ('USER', 'LEADER_GROUP') AND target_user_id IS NOT NULL)
            OR
            (scope_type NOT IN ('USER', 'LEADER_GROUP') AND target_user_id IS NULL)
        )
);

-- One manual job per requester, but different requesters can check together.
CREATE UNIQUE INDEX IF NOT EXISTS ux_check_runs_one_active_per_user
    ON public.check_runs(requested_by)
    WHERE requested_by IS NOT NULL
      AND trigger_type = 'MANUAL'
      AND status IN ('QUEUED', 'RUNNING');

-- Never overlap two scheduled company checks.
CREATE UNIQUE INDEX IF NOT EXISTS ux_check_runs_one_active_schedule
    ON public.check_runs ((trigger_type))
    WHERE trigger_type = 'SCHEDULED'
      AND status IN ('QUEUED', 'RUNNING');

CREATE INDEX IF NOT EXISTS ix_check_runs_status_priority_created
    ON public.check_runs(status, priority, created_at);

CREATE INDEX IF NOT EXISTS ix_check_runs_requested_by_created
    ON public.check_runs(requested_by, created_at DESC);

DROP TRIGGER IF EXISTS trg_check_runs_set_updated_at ON public.check_runs;
CREATE TRIGGER trg_check_runs_set_updated_at
BEFORE UPDATE ON public.check_runs
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- app_settings
-- Exactly one row. Secrets/proxy credentials belong in server environment
-- variables, never in this table or frontend.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.app_settings (
    id smallint PRIMARY KEY DEFAULT 1
        CHECK (id = 1),

    auto_check_enabled boolean NOT NULL DEFAULT false,
    check_interval_minutes integer NOT NULL DEFAULT 60
        CHECK (check_interval_minutes BETWEEN 15 AND 1440),
    timezone text NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    next_auto_check_at timestamptz NULL,
    last_auto_check_at timestamptz NULL,

    max_total_workers smallint NOT NULL DEFAULT 10
        CHECK (max_total_workers BETWEEN 1 AND 50),
    max_workers_per_job smallint NOT NULL DEFAULT 3
        CHECK (max_workers_per_job BETWEEN 1 AND 20),
    request_delay_seconds numeric(6, 2) NOT NULL DEFAULT 0.30
        CHECK (request_delay_seconds BETWEEN 0 AND 60),
    request_timeout_seconds integer NOT NULL DEFAULT 12
        CHECK (request_timeout_seconds BETWEEN 3 AND 120),
    retry_count smallint NOT NULL DEFAULT 2
        CHECK (retry_count BETWEEN 0 AND 5),
    dead_confirmation_attempts smallint NOT NULL DEFAULT 2
        CHECK (dead_confirmation_attempts BETWEEN 2 AND 5),

    follower_change_threshold bigint NOT NULL DEFAULT 1
        CHECK (follower_change_threshold >= 1),
    in_app_notifications_enabled boolean NOT NULL DEFAULT true,
    voice_notifications_enabled boolean NOT NULL DEFAULT false,

    updated_by uuid NULL
        REFERENCES public.users(id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT app_settings_per_job_not_above_total
        CHECK (max_workers_per_job <= max_total_workers),
    CONSTRAINT app_settings_timezone_not_blank
        CHECK (char_length(btrim(timezone)) > 0)
);

INSERT INTO public.app_settings (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;

DROP TRIGGER IF EXISTS trg_app_settings_set_updated_at ON public.app_settings;
CREATE TRIGGER trg_app_settings_set_updated_at
BEFORE UPDATE ON public.app_settings
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Supabase safety boundary
-- Browser never accesses these tables directly. FastAPI connects server-side
-- and enforces role permissions. RLS with no public policies blocks an
-- accidentally exposed anon/authenticated Supabase key.
-- ---------------------------------------------------------------------------

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.machines ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tiktok_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.check_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_settings ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.users IS
    'Internal BOSS, LEADER and MEMBER users; password_hash is Argon2id.';
COMMENT ON TABLE public.machines IS
    'Numbered machines 1..10 belonging to an internal user.';
COMMENT ON TABLE public.tiktok_accounts IS
    'One shared bounded row per TikTok username; never duplicated by checker role.';
COMMENT ON TABLE public.check_runs IS
    'Independent manual/scheduled jobs; old completed rows are cleaned by FastAPI.';
COMMENT ON TABLE public.app_settings IS
    'Singleton non-secret checker and scheduler settings.';
COMMENT ON COLUMN public.tiktok_accounts.total_sample_views IS
    'Sum of views from the recent public video sample, not guaranteed lifetime views.';
COMMENT ON COLUMN public.tiktok_accounts.recent_videos IS
    'Latest public video sample only; overwritten after a successful check.';
COMMENT ON COLUMN public.tiktok_accounts.auto_followers IS
    'Latest successful scheduled follower snapshot; manual checks do not rotate it.';

COMMIT;
