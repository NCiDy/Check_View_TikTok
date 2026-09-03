import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Laptop, LogOut, Shield } from "lucide-react";
import { api, notify } from "../api";
import type { LoginSession } from "../types";
import { formatTime } from "../utils";

export function SessionsPage() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["sessions"], queryFn: () => api<{ sessions: LoginSession[] }>("/api/sessions") });
  const revoke = useMutation({
    mutationFn: (id: string) => api<{ current_session_revoked: boolean }>(`/api/sessions/${id}`, { method: "DELETE" }),
    onSuccess: () => { notify("Đã thu hồi phiên đăng nhập", "success"); void queryClient.invalidateQueries({ queryKey: ["sessions"] }); },
    onError: (error) => notify((error as Error).message, "error"),
  });
  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">BẢO MẬT</p><h1>Phiên đăng nhập</h1><p>Mỗi tài khoản chỉ có một thiết bị hoạt động tại một thời điểm.</p></div><span className="heading-symbol"><Shield size={24} /></span></div><section className="session-grid">{data?.sessions.map((session) => <article className={`session-card ${session.revoked_at ? "session-revoked" : ""}`} key={session.id}><div className="session-icon"><Laptop size={22} /></div><div className="session-info"><div><strong>{session.user_name}</strong>{session.is_current && <span className="current-pill">Thiết bị này</span>}</div><span>{session.role} · @{session.username}</span><small>{session.user_agent || "Không rõ trình duyệt"}</small><div className="session-meta"><span>IP: {session.ip_address || "—"}</span><span>Hoạt động: {formatTime(session.last_seen_at)}</span><span>Đăng nhập: {formatTime(session.created_at)}</span></div></div><div className="session-action"><span className={session.revoked_at ? "state-disabled" : session.is_online ? "state-active" : "muted"}>{session.revoked_at ? "Đã thu hồi" : session.is_online ? "Online" : "Không hoạt động"}</span>{!session.revoked_at && !session.is_current && <button className="button danger small" onClick={() => window.confirm(`Đăng xuất ${session.user_name}?`) && revoke.mutate(session.id)}><LogOut size={15} /> Đăng xuất</button>}</div></article>)}{!data?.sessions.length && <div className="panel empty-state">Chưa có phiên đăng nhập.</div>}</section></div>;
}
