import { useQuery } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import { api } from "../api";
import type { AuditLog } from "../types";
import { formatTime } from "../utils";

const actionLabels: Record<string, string> = {
  AUTH_LOGIN: "Đăng nhập", AUTH_LOGOUT: "Đăng xuất", USER_CREATED: "Tạo người dùng",
  USER_UPDATED: "Cập nhật người dùng", PASSWORD_RESET: "Reset mật khẩu",
  PASSWORD_CHANGED: "Đổi mật khẩu", MACHINE_CREATED: "Thêm máy", MACHINE_DELETED: "Xóa máy",
  ACCOUNTS_ADDED: "Thêm kênh", ACCOUNT_DELETED: "Xóa kênh", ACCOUNT_TRANSFERRED: "Chuyển kênh",
  CHECK_STARTED: "Bắt đầu check", CHECK_STOP_REQUESTED: "Dừng check", SETTINGS_UPDATED: "Đổi cấu hình",
  SESSION_REVOKED: "Thu hồi phiên", AVATAR_UPDATED: "Đổi ảnh đại diện",
};

export function AuditPage() {
  const { data } = useQuery({ queryKey: ["audit"], queryFn: () => api<{ logs: AuditLog[] }>("/api/audit-logs?limit=150") });
  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">NHẬT KÝ</p><h1>Hoạt động hệ thống</h1><p>Chỉ lưu hành động quản trị, không lưu mật khẩu hoặc secret.</p></div><span className="heading-symbol"><ClipboardList size={24} /></span></div><section className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Thời gian</th><th>Người thực hiện</th><th>Hành động</th><th>Đối tượng</th><th>IP</th></tr></thead><tbody>{data?.logs.map((log) => <tr key={log.id}><td>{formatTime(log.created_at)}</td><td><strong>{log.actor_name}</strong></td><td><span className="audit-action">{actionLabels[log.action] || log.action}</span></td><td>{log.entity_type}<small>{log.entity_id}</small></td><td>{log.ip_address || "—"}</td></tr>)}{!data?.logs.length && <tr><td colSpan={5}><div className="empty-state">Chưa có nhật ký.</div></td></tr>}</tbody></table></div></section></div>;
}
