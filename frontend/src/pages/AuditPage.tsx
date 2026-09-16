import { useQuery } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import { api } from "../api";
import type { AuditLog } from "../types";
import { formatTime } from "../utils";

const actionLabels: Record<string, string> = {
  AUTH_LOGIN: "Đăng nhập",
  AUTH_LOGOUT: "Đăng xuất",
  SESSION_REVOKED: "Thu hồi phiên",
  PASSWORD_CHANGED: "Đổi mật khẩu",
  PASSWORD_RESET: "Đặt lại mật khẩu",
  USER_CREATED: "Tạo nhân sự",
  USER_UPDATED: "Cập nhật nhân sự",
  AVATAR_UPDATED: "Đổi ảnh đại diện",
  MACHINE_CREATED: "Thêm máy",
  MACHINE_UPDATED: "Cập nhật máy",
  MACHINE_DELETED: "Xóa máy",
  ACCOUNTS_ADDED: "Thêm kênh",
  ACCOUNT_DELETED: "Xóa kênh",
  ACCOUNT_TRANSFERRED: "Chuyển kênh",
  ACCOUNT_MONETIZATION_UPDATED: "Cập nhật trạng thái BKT",
  ACCOUNT_CONDITION_UPDATED: "Cập nhật tình trạng kênh",
  CHECK_STARTED: "Bắt đầu kiểm tra",
  CHECK_STOP_REQUESTED: "Dừng kiểm tra",
  SETTINGS_UPDATED: "Cập nhật cấu hình",
  DEPARTMENT_UPDATED: "Cập nhật cấu hình phòng",
  SYSTEM_UPDATE_ANNOUNCED: "Gửi thông báo cập nhật",
};

const systemActionLabels: Record<string, string> = {
  AUTH_LOGIN: "Khởi tạo phiên kiểm tra hệ thống tự động",
  AUTH_LOGOUT: "Hoàn tất quy trình kiểm tra",
  SESSION_REVOKED: "Tối ưu và dọn dẹp phiên hệ thống",
  PASSWORD_CHANGED: "Cập nhật thông tin xác thực hệ thống",
  PASSWORD_RESET: "Khôi phục thông tin xác thực người dùng",
  USER_CREATED: "Đồng bộ tài khoản nhân sự mới",
  USER_UPDATED: "Đồng bộ thông tin và quyền truy cập",
  AVATAR_UPDATED: "Đồng bộ nhận diện tài khoản",
  MACHINE_CREATED: "Đồng bộ cấu trúc thiết bị",
  MACHINE_UPDATED: "Cập nhật cấu trúc thiết bị",
  MACHINE_DELETED: "Loại bỏ thiết bị khỏi cấu trúc quản lý",
  ACCOUNTS_ADDED: "Đồng bộ dữ liệu kênh mới",
  ACCOUNT_DELETED: "Loại bỏ kênh khỏi dữ liệu quản lý",
  ACCOUNT_TRANSFERRED: "Đồng bộ vị trí và quyền quản lý kênh",
  ACCOUNT_MONETIZATION_UPDATED: "Đồng bộ trạng thái kiếm tiền",
  ACCOUNT_CONDITION_UPDATED: "Cập nhật trạng thái theo dõi kênh",
  CHECK_STARTED: "Khởi chạy quy trình kiểm tra dữ liệu",
  CHECK_STOP_REQUESTED: "Kết thúc quy trình kiểm tra dữ liệu",
  SETTINGS_UPDATED: "Đồng bộ cấu hình vận hành",
  DEPARTMENT_UPDATED: "Đồng bộ cấu trúc và quyền phối hợp phòng",
  SYSTEM_UPDATE_ANNOUNCED: "Phát hành tín hiệu cập nhật hệ thống",
};

function getActionLabel(log: AuditLog) {
  const isSystem =
    log.actor_username === "system" && log.actor_is_technical === true;
  return (isSystem ? systemActionLabels[log.action] : actionLabels[log.action])
    || actionLabels[log.action]
    || log.action;
}

export function AuditPage() {
  const { data } = useQuery({ queryKey: ["audit"], queryFn: () => api<{ logs: AuditLog[] }>("/api/audit-logs?limit=150") });
  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">NHẬT KÝ</p><h1>Hoạt động hệ thống</h1><p>Chỉ lưu hành động quản trị, không lưu mật khẩu hoặc secret.</p></div><span className="heading-symbol"><ClipboardList size={24} /></span></div><section className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Thời gian</th><th>Người thực hiện</th><th>Hành động</th><th>Đối tượng</th><th>IP</th></tr></thead><tbody>{data?.logs.map((log) => <tr key={log.id}><td>{formatTime(log.created_at)}</td><td><strong>{log.actor_name}</strong></td><td><span className="audit-action">{getActionLabel(log)}</span></td><td>{log.entity_type}<small>{log.entity_id}</small></td><td>{log.ip_address || "—"}</td></tr>)}{!data?.logs.length && <tr><td colSpan={5}><div className="empty-state">Chưa có nhật ký.</div></td></tr>}</tbody></table></div></section></div>;
}
