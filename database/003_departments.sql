-- Phòng ban và quyền hợp tác giữa các Leader.
-- Có thể chạy lại an toàn nhiều lần.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- 1. Bảng phòng ban
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.departments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    leader_collaboration_enabled boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT departments_name_not_blank
        CHECK (char_length(btrim(name)) BETWEEN 1 AND 100)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_departments_name_normalized
    ON public.departments (lower(btrim(name)));

ALTER TABLE public.departments
    ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 2. Liên kết nhân sự với phòng
-- ---------------------------------------------------------------------------

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS department_id uuid NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_department_id_fkey'
          AND conrelid = 'public.users'::regclass
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_department_id_fkey
            FOREIGN KEY (department_id)
            REFERENCES public.departments(id)
            ON DELETE SET NULL;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS ix_users_department_id
    ON public.users(department_id);

-- ---------------------------------------------------------------------------
-- 3. Tạo hoặc cập nhật hai phòng mẫu
-- ---------------------------------------------------------------------------

UPDATE public.departments
SET
    name = 'VIP',
    leader_collaboration_enabled = true,
    is_active = true,
    updated_at = now()
WHERE lower(btrim(name)) = 'vip';

INSERT INTO public.departments (
    name,
    leader_collaboration_enabled,
    is_active
)
SELECT
    'VIP',
    true,
    true
WHERE NOT EXISTS (
    SELECT 1
    FROM public.departments
    WHERE lower(btrim(name)) = 'vip'
);

UPDATE public.departments
SET
    name = 'Premium',
    leader_collaboration_enabled = false,
    is_active = true,
    updated_at = now()
WHERE lower(btrim(name)) = 'premium';

INSERT INTO public.departments (
    name,
    leader_collaboration_enabled,
    is_active
)
SELECT
    'Premium',
    false,
    true
WHERE NOT EXISTS (
    SELECT 1
    FROM public.departments
    WHERE lower(btrim(name)) = 'premium'
);

-- ---------------------------------------------------------------------------
-- 4. Gán Leader vào phòng
-- ---------------------------------------------------------------------------

UPDATE public.users
SET department_id = (
    SELECT id
    FROM public.departments
    WHERE lower(btrim(name)) = 'vip'
    LIMIT 1
)
WHERE role = 'LEADER'
  AND username_normalized IN (
      'cuongkid',
      'quinnxinkdep'
  );

UPDATE public.users
SET department_id = (
    SELECT id
    FROM public.departments
    WHERE lower(btrim(name)) = 'premium'
    LIMIT 1
)
WHERE role = 'LEADER'
  AND username_normalized IN (
      'leadhien',
      'leadngan'
  );

-- ---------------------------------------------------------------------------
-- 5. Member tự động nhận cùng phòng với Leader quản lý
-- ---------------------------------------------------------------------------

UPDATE public.users AS member
SET department_id = leader.department_id
FROM public.users AS leader
WHERE member.role = 'MEMBER'
  AND member.leader_id = leader.id
  AND leader.role = 'LEADER'
  AND leader.department_id IS NOT NULL
  AND member.department_id IS DISTINCT FROM leader.department_id;

COMMIT;

-- ---------------------------------------------------------------------------
-- 6. Kiểm tra kết quả
-- ---------------------------------------------------------------------------

SELECT
    u.full_name,
    u.username,
    u.role,
    leader.full_name AS leader_name,
    d.name AS department,
    d.leader_collaboration_enabled AS collaboration_enabled
FROM public.users AS u
LEFT JOIN public.users AS leader
    ON leader.id = u.leader_id
LEFT JOIN public.departments AS d
    ON d.id = u.department_id
ORDER BY
    d.name NULLS LAST,
    CASE u.role
        WHEN 'BOSS' THEN 1
        WHEN 'MANAGER' THEN 2
        WHEN 'LEADER' THEN 3
        WHEN 'MEMBER' THEN 4
        ELSE 5
    END,
    u.full_name;