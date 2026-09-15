import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Camera,
  Edit3,
  Handshake,
  LockKeyhole,
  Plus,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { api, notify } from "../api";
import { useAuth } from "../AuthContext";
import { Avatar } from "../components/Avatar";
import { Modal } from "../components/Modal";
import type { Department, Role, User } from "../types";
import { formatTime } from "../utils";

export function PeoplePage() {
  const { user: current } = useAuth();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<User | "new" | null>(null);
  const { data } = useQuery({ queryKey: ["users"], queryFn: () => api<{ users: User[] }>("/api/users") });
  const users = data?.users || [];

  const departmentsQuery = useQuery({
    queryKey: ["departments"],
    queryFn: () =>
      api<{
        departments: Department[];
      }>("/api/departments"),
  });

  const departments = departmentsQuery.data?.departments || [];

  const updateDepartment = useMutation({
    mutationFn: ({
      id,
      enabled,
    }: {
      id: string;
      enabled: boolean;
    }) =>
      api(`/api/departments/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          leader_collaboration_enabled: enabled,
        }),
      }),

    onSuccess: async () => {
      notify("Đã cập nhật quyền hợp tác của phòng", "success");

      await queryClient.invalidateQueries({
        queryKey: ["departments"],
      });

      await queryClient.invalidateQueries({
        queryKey: ["users"],
      });
    },

    onError: (error) =>
      notify((error as Error).message, "error"),
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["users"] });
    await queryClient.invalidateQueries({ queryKey: ["organization"] });
    await queryClient.invalidateQueries({ queryKey: ["departments"] });
  }

  async function uploadAvatar(target: User, file?: File) {
    if (!file) return;
    const form = new FormData();
    form.append("avatar", file);
    try {
      await api(`/api/users/${target.id}/avatar`, { method: "POST", body: form });
      notify("Đã cập nhật ảnh đại diện", "success");
      await refresh();
    } catch (error) { notify((error as Error).message, "error"); }
  }

  return (
    <div className="page-stack">
      <div className="page-heading"><div><p className="eyebrow">QUẢN TRỊ</p><h1>Nhân sự và quyền</h1><p>Quản lý tài khoản đăng nhập, phạm vi và quyền thao tác.</p></div><button className="button primary" onClick={() => setEditing("new")}><Plus size={17} /> Thêm nhân sự</button></div>
      <section className="panel department-settings">
        <div className="section-heading">
          <div>
            <p className="eyebrow">PHÒNG BAN</p>
            <h2>Quyền hợp tác</h2>
          </div>
        </div>

        <div className="department-setting-list">
          {departments.map((department) => (
            <div
              className="department-setting-row"
              key={department.id}
            >
              <span className="department-setting-name">
                {department.leader_collaboration_enabled ? (
                  <Handshake size={18} />
                ) : (
                  <LockKeyhole size={18} />
                )}

                <span>
                  <strong>Phòng {department.name}</strong>
                  <small>
                    {department.leader_collaboration_enabled
                      ? "Leader được xem và check toàn phòng"
                      : "Leader chỉ xem nhóm trực thuộc"}
                  </small>
                </span>
              </span>

              <label className="switch-control">
                <input
                  type="checkbox"
                  checked={
                    department.leader_collaboration_enabled
                  }
                  disabled={updateDepartment.isPending}
                  onChange={(event) =>
                    updateDepartment.mutate({
                      id: department.id,
                      enabled: event.target.checked,
                    })
                  }
                />

                <span />
              </label>
            </div>
          ))}
        </div>
      </section>
      <section className="panel table-panel">
        <div className="table-scroll"><table><thead><tr><th>Nhân sự</th><th>Vai trò</th><th>Phạm vi</th><th>Quyền</th><th>Hoạt động</th><th /></tr></thead><tbody>
          {users.map((person) => <tr key={person.id}>
            <td><div className="account-cell"><label className="avatar-upload" title="Đổi ảnh"><Avatar name={person.full_name} url={person.avatar_url} /><Camera size={12} /><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => void uploadAvatar(person, e.target.files?.[0])} /></label><span><strong>{person.full_name}</strong><small>@{person.username}</small></span></div></td>
            <td><span className={`role-pill role-${person.role.toLowerCase()}`}>{person.is_system_owner && <ShieldCheck size={13} />} {person.role}</span></td>
            <td>{person.machine_count} máy · {person.account_count} kênh</td>
            <td><div className="permission-list"><span className={person.can_add_accounts || ["BOSS", "MANAGER"].includes(person.role) ? "on" : ""}>Thêm</span><span className={person.can_delete_accounts || ["BOSS", "MANAGER"].includes(person.role) ? "on" : ""}>Xóa</span><span className={person.can_run_checks || ["BOSS", "MANAGER"].includes(person.role) ? "on" : ""}>Check</span></div></td>
            <td><span className={person.is_active ? "state-active" : "state-disabled"}>{person.is_active ? (person.is_online ? "Đang online" : "Đang hoạt động") : "Đã khóa"}</span><small>{formatTime(person.last_seen_at)}</small></td>
            <td>{(!["BOSS", "MANAGER"].includes(person.role) || current?.is_system_owner) && <button className="icon-button" onClick={() => setEditing(person)}><Edit3 size={17} /></button>}</td>
          </tr>)}
        </tbody></table></div>
      </section>
      {editing && <UserDialog user={editing === "new" ? null : editing} users={users} current={current!} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void refresh(); }} />}
    </div>
  );
}

function UserDialog({ user, users, current, onClose, onSaved }: { user: User | null; users: User[]; current: User; onClose: () => void; onSaved: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [role, setRole] = useState<Role>(user?.role || "LEADER");
  const [leaderId, setLeaderId] = useState(user?.leader_id || "");
  const [canAdd, setCanAdd] = useState(user?.can_add_accounts || false);
  const [canDelete, setCanDelete] = useState(user?.can_delete_accounts || false);
  const [canCheck, setCanCheck] = useState(user?.can_run_checks ?? true);
  const [active, setActive] = useState(user?.is_active ?? true);
  const [showOrg, setShowOrg] = useState(user?.show_in_org_chart ?? true);

  const save = useMutation({
    mutationFn: () => {
      if (user) {
        return api(`/api/users/${user.id}`, { method: "PATCH", body: JSON.stringify({ full_name: fullName, is_active: active, can_add_accounts: canAdd, can_delete_accounts: canDelete, can_run_checks: canCheck, show_in_org_chart: showOrg, ...(user.role === "MEMBER" ? { leader_id: leaderId } : {}) }) });
      }
      return api("/api/users", { method: "POST", body: JSON.stringify({ username, password, full_name: fullName, role, leader_id: role === "MEMBER" ? leaderId : null, can_add_accounts: canAdd, can_delete_accounts: canDelete, can_run_checks: canCheck, show_in_org_chart: showOrg }) });
    },
    onSuccess: () => { notify(user ? "Đã cập nhật nhân sự" : "Đã tạo tài khoản", "success"); onSaved(); },
    onError: (error) => notify((error as Error).message, "error"),
  });

  async function resetPassword() {
    if (!user) return;
    const next = window.prompt(`Nhập mật khẩu mới cho ${user.full_name} (ít nhất 8 ký tự):`);
    if (!next) return;
    try {
      await api(`/api/users/${user.id}/reset-password`, { method: "POST", body: JSON.stringify({ new_password: next }) });
      notify("Đã đặt lại mật khẩu và đăng xuất phiên cũ", "success");
    } catch (error) { notify((error as Error).message, "error"); }
  }

  const leaders = users.filter((item) => item.role === "LEADER" && item.is_active);
  return <Modal title={user ? `Sửa ${user.full_name}` : "Thêm tài khoản"} onClose={onClose}><form className="form-stack" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}><div className="form-grid">
    {!user && <><label>Tên đăng nhập<input value={username} onChange={(e) => setUsername(e.target.value)} minLength={3} required autoFocus /></label><label>Mật khẩu ban đầu<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={8} required /></label></>}
    <label className={user ? "full-row" : ""}>Họ tên<input value={fullName} onChange={(e) => setFullName(e.target.value)} required /></label>
    {!user && <label>Vai trò<select value={role} onChange={(e) => setRole(e.target.value as Role)}><option value="LEADER">LEADER</option><option value="MEMBER">MEMBER</option>{current.is_system_owner && (<><option value="MANAGER">QUẢN LÝ</option><option value="BOSS">BOSS</option></>)}</select></label>}
    {(role === "MEMBER" || user?.role === "MEMBER") && <label className="full-row">Leader quản lý<select required value={leaderId} onChange={(e) => setLeaderId(e.target.value)}><option value="">Chọn Leader</option>{leaders.map((leader) => <option key={leader.id} value={leader.id}>{leader.full_name}</option>)}</select></label>}
  </div>
  {!["BOSS", "MANAGER"].includes(role) && !["BOSS", "MANAGER"].includes(user?.role || "") && <div className="checkbox-grid"><label><input type="checkbox" checked={canAdd} onChange={(e) => setCanAdd(e.target.checked)} /> Tự thêm máy/kênh</label><label><input type="checkbox" checked={canDelete} onChange={(e) => setCanDelete(e.target.checked)} /> Tự xóa máy/kênh</label><label><input type="checkbox" checked={canCheck} onChange={(e) => setCanCheck(e.target.checked)} /> Được check</label></div>}
  <div className="checkbox-grid"><label><input type="checkbox" checked={showOrg} onChange={(e) => setShowOrg(e.target.checked)} /> Hiện trong sơ đồ</label>{user && !user.is_system_owner && <label><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Tài khoản hoạt động</label>}</div>
  <div className="modal-actions">{user && <button type="button" className="button danger ghost" onClick={resetPassword}>Reset mật khẩu</button>}<button type="button" className="button secondary" onClick={onClose}>Hủy</button><button className="button primary" disabled={save.isPending}>{user ? "Lưu thay đổi" : "Tạo tài khoản"}</button></div></form></Modal>;
}
