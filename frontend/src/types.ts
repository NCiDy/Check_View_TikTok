export type Role = "BOSS" | "MANAGER" | "LEADER" | "MEMBER";

export interface User {
  id: string;
  username: string;
  full_name: string;
  avatar_url?: string | null;
  role: Role;
  leader_id?: string | null;
  is_system_owner: boolean;
  is_technical_account: boolean;
  show_in_org_chart: boolean;
  is_active: boolean;
  can_add_accounts: boolean;
  can_delete_accounts: boolean;
  can_run_checks: boolean;
  machine_count: number;
  account_count: number;
  last_login_at?: string | null;
  last_seen_at?: string | null;
  is_online: boolean;
  created_at?: string | null;
  department_id?: string | null;
}

export interface Department {
  id: string;
  name: string;
  leader_collaboration_enabled: boolean;
}

export interface Machine {
  id: string;
  owner_id: string;
  machine_number: number;
  machine_type: "NORMAL" | "MONETIZED";
  note?: string | null;
  account_count: number;
  created_at?: string | null;
}

export interface RecentVideo {
  id?: string;
  desc?: string;
  play_count?: number;
  cover_url?: string;
  video_url?: string;
  ratio?: string;
}

export interface TikTokAccount {
  id: string;
  machine_id: string;
  machine_number: number;
  machine_type: "NORMAL" | "MONETIZED";
  slot_number: number;
  owner_id: string;
  owner_name: string;
  owner_role: Role;
  username: string;
  nickname?: string | null;
  avatar_url?: string | null;
  bio?: string | null;
  followers?: number | null;
  previous_followers?: number | null;
  follower_delta?: number | null;
  following?: number | null;
  total_likes?: number | null;
  total_sample_views?: number | null;
  avg_sample_views?: number | null;
  video_count_sample: number;
  recent_videos: RecentVideo[];
  status: "LIVE" | "DIE" | "ERROR" | "UNCHECKED";
  previous_status?: string | null;
  is_private: boolean;
  is_verified: boolean;
  is_monetized: boolean;
  monetized_at?: string | null;
  last_error_code?: string | null;
  last_error_message?: string | null;
  last_checked_at?: string | null;
  last_successful_checked_at?: string | null;
}

export interface Dashboard {
  total: number;
  live: number;
  die: number;
  error: number;
  unchecked: number;
  new_problem: number;
  last_checked_at?: string | null;
  recent_changes: Array<{
    account_id: string;
    owner_id: string;
    username: string;
    owner_name: string;
    machine_number: number;
    slot_number: number;
    before: number;
    after: number;
    delta: number;
    checked_at?: string | null;
  }>;
}

export interface CheckRun {
  id: string;
  requested_by?: string | null;
  requested_session_id?: string | null;
  trigger_type?: "MANUAL" | "SCHEDULED";
  scope_type?: string;
  target_user_id?: string | null;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "STOPPED" | "FAILED";
  total_accounts: number;
  processed_accounts?: number;
  progress_percent?: number;
  live_count?: number;
  die_count?: number;
  error_count?: number;
  follower_changed_count?: number;
  new_problem_count?: number;
  message?: string | null;
}

export interface AppSettings {
  auto_check_enabled: boolean;
  check_interval_minutes: number;
  timezone: string;
  next_auto_check_at?: string | null;
  last_auto_check_at?: string | null;
  follower_change_threshold: number;
  monetization_follower_threshold: number;
  voice_notifications_enabled: boolean;
  max_total_workers?: number;
  max_workers_per_job?: number;
  request_delay_seconds?: number;
  request_timeout_seconds?: number;
  retry_count?: number;
  dead_confirmation_attempts?: number;
  in_app_notifications_enabled?: boolean;
}

export interface LoginSession {
  id: string;
  user_id: string;
  user_name: string;
  username?: string | null;
  role?: Role | null;
  ip_address?: string | null;
  user_agent?: string | null;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  revoked_at?: string | null;
  revoked_reason?: string | null;
  is_current: boolean;
  is_online: boolean;
}

export interface AuditLog {
  id: number;
  actor_user_id?: string | null;
  actor_name: string;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  details: Record<string, unknown>;
  ip_address?: string | null;
  created_at: string;
}
