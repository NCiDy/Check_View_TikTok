import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRightLeft, Eye, Plus, Search, Smartphone, Trash2 } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { api, notify } from "../api";
import { useAuth } from "../AuthContext";
import { Avatar } from "../components/Avatar";
import { Modal } from "../components/Modal";
import { useStartCheck } from "../hooks/useStartCheck";
import type {
  Department,
  Machine,
  TikTokAccount,
  User,
} from "../types";
import { formatNumber, formatTime, statusLabel } from "../utils";

type Dialog = "machine" | "accounts" | "detail" | "transfer" | null;

export function AccountsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const check = useStartCheck();
  const [params, setParams] = useSearchParams();
  const [dialog, setDialog] = useState<Dialog>(null);
  const [detail, setDetail] = useState<TikTokAccount | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [machineId, setMachineId] = useState("ALL");
  const [search, setSearch] = useState("");
  const ownerId = params.get("owner") || user?.id || "";
  const status = params.get("status") || "ALL";

  const isCompanyAdmin = user?.role === "BOSS" || user?.role === "MANAGER";
  const usersQuery = useQuery({ queryKey: ["users"], queryFn: () => api<{ users: User[] }>("/api/users") });
  const organizationQuery = useQuery({
    queryKey: ["organization"],
    queryFn: () =>
      api<{
        users: User[];
        departments: Department[];
      }>("/api/organization"),
  });

  const departments =
    organizationQuery.data?.departments || [];
  const machinesQuery = useQuery({
    queryKey: ["machines", ownerId],
    queryFn: () => api<{ machines: Machine[] }>(`/api/machines?owner_id=${encodeURIComponent(ownerId)}`),
    enabled: Boolean(ownerId && ownerId !== "ALL"),
  });
  const accountsQuery = useQuery({
    queryKey: ["accounts", ownerId],
    queryFn: () => api<{ accounts: TikTokAccount[] }>(`/api/accounts?owner_id=${encodeURIComponent(ownerId)}`),
    enabled: Boolean(ownerId),
  });

  const owner = usersQuery.data?.users.find((item) => item.id === ownerId);
    const isOwnAccount = owner?.id === user?.id;

  const isManagedMember = Boolean(
    user?.role === "LEADER" &&
    owner?.role === "MEMBER" &&
    owner.leader_id === user.id
  );

  const canAdd = Boolean(
    owner &&
    (
      isCompanyAdmin ||
      ((isOwnAccount || isManagedMember) && user?.can_add_accounts)
    )
  );

  const canDelete = Boolean(
    owner &&
    (
      isCompanyAdmin ||
      ((isOwnAccount || isManagedMember) && user?.can_delete_accounts)
    )
  );

  const canCheck = Boolean(
    isCompanyAdmin || user?.can_run_checks
  );

  const filtered = useMemo(() => (accountsQuery.data?.accounts || []).filter((account) => {
    if (machineId !== "ALL" && account.machine_id !== machineId) return false;
    if (search && !account.username.toLowerCase().includes(search.toLowerCase())) return false;
    if (status === "ERROR") return ["ERROR", "UNCHECKED"].includes(account.status);
    if (status !== "ALL" && account.status !== status) return false;
    return true;
  }), [accountsQuery.data, machineId, search, status]);

  function selectOwner(id: string) {
    setParams({ owner: id, status: "ALL" });
    setMachineId("ALL");
    setSelected(new Set());
  }

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["accounts"] }),
      queryClient.invalidateQueries({ queryKey: ["machines"] }),
      queryClient.invalidateQueries({ queryKey: ["users"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
    ]);
  }

  const deleteMachine = useMutation({
    mutationFn: (id: string) => api(`/api/machines/${id}`, { method: "DELETE" }),
    onSuccess: () => { notify("Đã xóa máy và các kênh thuộc máy", "success"); void refresh(); },
    onError: (error) => notify((error as Error).message, "error"),
  });

  const deleteAccount = useMutation({
    mutationFn: (id: string) => api(`/api/accounts/${id}`, { method: "DELETE" }),
    onSuccess: () => { notify("Đã xóa kênh", "success"); setDialog(null); void refresh(); },
    onError: (error) => notify((error as Error).message, "error"),
  });

  const groups = useMemo(() => {
    const all = usersQuery.data?.users || [];

    return {
      bosses: all.filter((item) => item.role === "BOSS"),
      managers: all.filter((item) => item.role === "MANAGER"),
      leaders: all.filter((item) => item.role === "LEADER"),
      members: all.filter((item) => item.role === "MEMBER"),
    };
  }, [usersQuery.data]);

    const activeBosses = groups.bosses.filter((item) => item.is_active);
    const activeManagers = groups.managers.filter(
      (item) => item.is_active
    );

  const activeLeaders = groups.leaders.filter(
    (leader) => leader.is_active
  );

  const activeMembers = groups.members.filter(
    (member) => member.is_active
  );

  const departmentGroups = departments.map((department) => {
    const leaders = activeLeaders
      .filter(
        (leader) =>
          leader.department_id === department.id
      )
      .map((leader) => ({
        leader,
        members: activeMembers.filter(
          (member) => member.leader_id === leader.id
        ),
      }));

    return {
      department,
      leaders,
    };
  });

  const assignedLeaderIds = new Set(
    departmentGroups.flatMap((group) =>
      group.leaders.map((team) => team.leader.id)
    )
  );

  const unassignedTeams = activeLeaders
    .filter((leader) => !assignedLeaderIds.has(leader.id))
    .map((leader) => ({
      leader,
      members: activeMembers.filter(
        (member) => member.leader_id === leader.id
      ),
    }));

  const groupedMemberIds = new Set(
    [
      ...departmentGroups.flatMap((group) =>
        group.leaders.flatMap((team) => team.members)
      ),
      ...unassignedTeams.flatMap((team) => team.members),
    ].map((member) => member.id)
  );

  const standaloneMembers = activeMembers.filter(
    (member) => !groupedMemberIds.has(member.id)
  );

  function renderPerson(item: User, extraClass = "") {
    return (
      <button
        key={item.id}
        className={`person-row ${extraClass} ${
          ownerId === item.id ? "active" : ""
        }`}
        onClick={() => selectOwner(item.id)}
      >
        <Avatar
          name={item.full_name}
          url={item.avatar_url}
          size="sm"
        />

        <span>
          <strong>{item.full_name}</strong>
          <small>
            {item.role} · {item.account_count} kênh
          </small>
        </span>

        {item.is_online && (
          <i className="online-dot" title="Đang online" />
        )}
      </button>
    );
  }

  return (
    <div className="accounts-layout">
      <aside className="people-rail panel">
        <div className="rail-heading"><div><p className="eyebrow">PHẠM VI</p><h2>Nhân sự</h2></div></div>
        {isCompanyAdmin && <button className={`person-row ${ownerId === "ALL" ? "active" : ""}`} onClick={() => selectOwner("ALL")}><span className="avatar avatar-sm">CT</span><span><strong>Toàn công ty</strong><small>Tất cả kênh</small></span></button>}
                <div className="company-people">
          {activeBosses.length > 0 && (
            <div className="boss-section">
              {activeBosses.map((boss) => renderPerson(boss))}
            </div>
          )}
          {activeManagers.length > 0 && (
            <div className="manager-section">
              <div className="scope-team-label">Quản lý</div>

              {activeManagers.map((manager) =>
                renderPerson(manager, "team-manager")
              )}
            </div>
          )}

          {departmentGroups.map(({ department, leaders }) => (
            <div className="scope-department" key={department.id}>
              <div className="scope-department-heading">
                <strong>Phòng {department.name}</strong>

                <small
                  className={
                    department.leader_collaboration_enabled
                      ? "collaboration-on"
                      : ""
                  }
                >
                  {department.leader_collaboration_enabled
                    ? "Hợp tác"
                    : "Riêng nhóm"}
                </small>
              </div>

              {leaders.map(({ leader, members }) => (
                <div className="scope-team" key={leader.id}>
                  {renderPerson(leader, "team-leader")}

                  {members.length > 0 && (
                    <div className="team-members">
                      {members.map((member) =>
                        renderPerson(member, "team-member")
                      )}
                    </div>
                  )}
                </div>
              ))}

              {!leaders.length && (
                <div className="scope-empty">
                  Chưa có Leader
                </div>
              )}
            </div>
          ))}

          {unassignedTeams.length > 0 && (
            <div className="scope-department unassigned">
              <div className="scope-department-heading">
                <strong>Chưa phân phòng</strong>
              </div>

              {unassignedTeams.map(({ leader, members }) => (
                <div className="scope-team" key={leader.id}>
                  {renderPerson(leader, "team-leader")}

                  {members.length > 0 && (
                    <div className="team-members">
                      {members.map((member) =>
                        renderPerson(member, "team-member")
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {standaloneMembers.length > 0 && (
            <div className="scope-team standalone-team">
              <div className="scope-team-label">Chưa thuộc nhóm</div>

              <div className="team-members">
                {standaloneMembers.map((member) =>
                  renderPerson(member, "team-member")
                )}
              </div>
            </div>
          )}
        </div>
      </aside>

      <main className="page-stack min-width-0">
        <div className="page-heading compact">
          <div><p className="eyebrow">DANH SÁCH KÊNH</p><h1>{ownerId === "ALL" ? "Toàn công ty" : owner?.full_name || "Đang tải…"}</h1><p>{ownerId === "ALL" ? `${filtered.length} kênh có quyền xem` : `${owner?.machine_count || 0} máy · ${owner?.account_count || 0} kênh`}</p></div>
          <div className="heading-actions">
            {canAdd && <><button className="button secondary" onClick={() => setDialog("machine")}><Plus size={16} /> Thêm máy</button><button className="button secondary" disabled={!machinesQuery.data?.machines.length} onClick={() => setDialog("accounts")}><Plus size={16} /> Thêm kênh</button></>}
            {selected.size > 0 && canCheck && <button className="button secondary" onClick={() => check.mutate({ scope_type: "SELECTED", account_ids: [...selected] })}>Check {selected.size} kênh</button>}
            {user?.role === "BOSS" && owner?.role === "LEADER" && <button className="button secondary" onClick={() => window.confirm(`Check toàn bộ nhóm của ${owner.full_name}?`) && check.mutate({ scope_type: "LEADER_GROUP", target_user_id: owner.id })}>Check cả nhóm</button>}
            {ownerId !== "ALL" && canCheck && <button className="button primary" onClick={() => check.mutate({ scope_type: "USER", target_user_id: ownerId })}>Check người này</button>}
          </div>
        </div>

        {ownerId !== "ALL" && Boolean(machinesQuery.data?.machines.length) && (
          <div className="machine-tabs">
            <button className={machineId === "ALL" ? "active" : ""} onClick={() => setMachineId("ALL")}>Tất cả</button>
            {machinesQuery.data?.machines.map((machine) => <span key={machine.id} className="machine-tab-wrap"><button className={machineId === machine.id ? "active" : ""} onClick={() => setMachineId(machine.id)}><Smartphone size={14} /> Máy #{machine.machine_number} <small>{machine.account_count}/10</small></button>{canDelete && <button className="machine-delete" title="Xóa máy" onClick={() => window.confirm(`Xóa máy #${machine.machine_number} và toàn bộ kênh?`) && deleteMachine.mutate(machine.id)}>×</button>}</span>)}
          </div>
        )}

        <section className="panel table-panel">
          <div className="table-toolbar">
            <label className="search-box"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Tìm username…" /></label>
            <div className="filter-chips">{["ALL", "LIVE", "DIE", "ERROR", "UNCHECKED"].map((item) => <button key={item} className={status === item ? "active" : ""} onClick={() => setParams({ owner: ownerId, status: item })}>{item === "ALL" ? "Tất cả" : statusLabel(item)}</button>)}</div>
          </div>
          <div className="table-scroll">
            <table>
              <thead><tr><th><input type="checkbox" checked={Boolean(filtered.length && filtered.every((item) => selected.has(item.id)))} onChange={(e) => setSelected(e.target.checked ? new Set(filtered.map((item) => item.id)) : new Set())} /></th><th>Máy / Kênh</th><th>Tài khoản</th><th>Trạng thái</th><th>Followers</th><th>Tổng view mẫu</th><th>Lần check</th><th /></tr></thead>
              <tbody>
                {filtered.map((account) => <tr key={account.id}>
                  <td><input type="checkbox" checked={selected.has(account.id)} onChange={(e) => setSelected((old) => { const next = new Set(old); e.target.checked ? next.add(account.id) : next.delete(account.id); return next; })} /></td>
                  <td><strong>M#{account.machine_number} – K{account.slot_number}</strong><small>{account.owner_name}</small></td>
                  <td><div className="account-cell"><Avatar name={account.nickname || account.username} url={account.avatar_url} size="sm" /><span><strong>@{account.username}</strong><small>{account.nickname || "Chưa có nickname"}</small></span></div></td>
                  <td><span className={`status-badge status-${account.status.toLowerCase()}`}>{account.status === "LIVE" && account.is_private ? "LIVE · RIÊNG TƯ" : statusLabel(account.status)}</span>{account.last_error_message && <small title={account.last_error_message}>{account.last_error_code}</small>}</td>
                  <td><strong>{formatNumber(account.followers)}</strong>{account.follower_delta != null && account.follower_delta !== 0 && <small className={account.follower_delta > 0 ? "delta-positive" : "delta-negative"}>{account.follower_delta > 0 ? "+" : ""}{formatNumber(account.follower_delta)}</small>}</td>
                  <td>{formatNumber(account.total_sample_views)}</td>
                  <td>{formatTime(account.last_checked_at)}</td>
                  <td><button className="icon-button" title="Chi tiết" onClick={() => { setDetail(account); setDialog("detail"); }}><Eye size={17} /></button></td>
                </tr>)}
                {!filtered.length && <tr><td colSpan={8}><div className="empty-state">Chưa có kênh phù hợp.</div></td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      {dialog === "machine" && owner && <MachineDialog owner={owner} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); void refresh(); }} />}
      {dialog === "accounts" && owner && <AccountsDialog owner={owner} machines={machinesQuery.data?.machines || []} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); void refresh(); }} />}
            {dialog === "detail" && detail && (
        <Modal
          title={`Chi tiết @${detail.username}`}
          onClose={() => setDialog(null)}
          wide
        >
          <div className="detail-profile">
            <Avatar
              name={detail.nickname || detail.username}
              url={detail.avatar_url}
              size="lg"
            />

            <div>
              <h3>{detail.nickname || detail.username}</h3>
              <p>
                @{detail.username} · {detail.owner_name}
              </p>
            </div>
          </div>

          <div className="detail-grid">
            <span>
              Followers
              <strong>{formatNumber(detail.followers)}</strong>
            </span>

            <span>
              Following
              <strong>{formatNumber(detail.following)}</strong>
            </span>

            <span>
              Tổng tim
              <strong>{formatNumber(detail.total_likes)}</strong>
            </span>

            <span>
              Tổng view 10 video
              <strong>{formatNumber(detail.total_sample_views)}</strong>
            </span>
          </div>

          {detail.bio && <p className="bio-box">{detail.bio}</p>}

          <div className="recent-video-heading">
            <div>
              <h3>Video công khai gần đây</h3>
              <small>
                {detail.video_count_sample || 0} video được lấy trong lần check gần nhất
              </small>
            </div>

            {detail.avg_sample_views != null && (
              <span>
                Trung bình: {formatNumber(detail.avg_sample_views)} view
              </span>
            )}
          </div>

          {detail.recent_videos?.length ? (
            <div className="recent-video-grid">
              {detail.recent_videos.slice(0, 10).map((video, index) => (
                <article
                  className="recent-video-card"
                  key={video.id || `${detail.id}-${index}`}
                >
                  {video.cover_url ? (
                    <img
                      src={video.cover_url}
                      alt={`Video ${index + 1} của @${detail.username}`}
                      loading="lazy"
                    />
                  ) : (
                    <div className="video-no-cover">
                      Video {index + 1}
                    </div>
                  )}

                  <div className="recent-video-info">
                    <strong>
                      {formatNumber(video.play_count)} lượt xem
                    </strong>

                    <p title={video.desc || ""}>
                      {video.desc || "Không có mô tả"}
                    </p>

                    {video.video_url && (
                      <a
                        href={video.video_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Xem video trên TikTok
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="video-empty">
              {detail.is_private
                ? "Tài khoản riêng tư nên không lấy danh sách video."
                : "Chưa có video. Hãy check lại kênh này."}
            </div>
          )}

          <div className="modal-actions detail-actions">
            <a
              className="button secondary"
              href={`https://www.tiktok.com/@${encodeURIComponent(
                detail.username
              )}`}
              target="_blank"
              rel="noreferrer"
            >
              Mở trang TikTok
            </a>

            {user?.role === "BOSS" && (
              <button
                className="button secondary"
                onClick={() => setDialog("transfer")}
              >
                <ArrowRightLeft size={16} />
                Chuyển kênh
              </button>
            )}

            {canDelete && (
              <button
                className="button danger"
                onClick={() =>
                  window.confirm(`Xóa @${detail.username}?`) &&
                  deleteAccount.mutate(detail.id)
                }
              >
                <Trash2 size={16} />
                Xóa kênh
              </button>
            )}
          </div>
        </Modal>
      )}
      {dialog === "transfer" && detail && <TransferDialog account={detail} users={usersQuery.data?.users || []} onClose={() => setDialog("detail")} onSaved={() => { setDialog(null); void refresh(); }} />}
    </div>
  );
}

function MachineDialog({ owner, onClose, onSaved }: { owner: User; onClose: () => void; onSaved: () => void }) {
  const [number, setNumber] = useState("");
  const [note, setNote] = useState("");
  const mutation = useMutation({
    mutationFn: () => api("/api/machines", { method: "POST", body: JSON.stringify({ owner_id: owner.id, machine_number: Number(number), note: note || null }) }),
    onSuccess: () => { notify("Đã thêm máy", "success"); onSaved(); },
    onError: (error) => notify((error as Error).message, "error"),
  });
  return <Modal title={`Thêm máy cho ${owner.full_name}`} onClose={onClose}><form className="form-stack" onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }}><label>Số trên máy công ty<input type="number" min="1" max="32767" required value={number} onChange={(e) => setNumber(e.target.value)} placeholder="Ví dụ: 47" autoFocus /></label><label>Ghi chú<input maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Không bắt buộc" /></label><div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Hủy</button><button className="button primary" disabled={mutation.isPending}>Thêm máy</button></div></form></Modal>;
}

function AccountsDialog({ owner, machines, onClose, onSaved }: { owner: User; machines: Machine[]; onClose: () => void; onSaved: () => void }) {
  const [machineId, setMachineId] = useState(machines[0]?.id || "");
  const [items, setItems] = useState("");
  const [result, setResult] = useState<string[]>([]);
  const mutation = useMutation({
    mutationFn: () => api<{ added: Array<{ username: string }>; rejected: Array<{ input: string; reason: string }> }>("/api/accounts/bulk", { method: "POST", body: JSON.stringify({ machine_id: machineId, items: items.split(/\r?\n/).filter(Boolean) }) }),
    onSuccess: (data) => {
      setResult(data.rejected.map((item) => `${item.input}: ${item.reason}`));
      notify(`Đã thêm ${data.added.length} kênh`, "success");
      if (!data.rejected.length) onSaved();
    },
    onError: (error) => notify((error as Error).message, "error"),
  });
  return <Modal title={`Thêm kênh cho ${owner.full_name}`} onClose={onClose}><form className="form-stack" onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }}><label>Máy<select value={machineId} onChange={(e) => setMachineId(e.target.value)}>{machines.map((machine) => <option key={machine.id} value={machine.id}>Máy #{machine.machine_number} · còn {10 - machine.account_count} vị trí</option>)}</select></label><label>Username, mỗi dòng một kênh<textarea rows={9} required value={items} onChange={(e) => setItems(e.target.value)} placeholder={'@username\nhttps://tiktok.com/@username'} /></label>{result.length > 0 && <div className="error-list">{result.map((item) => <small key={item}>{item}</small>)}</div>}<div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Đóng</button><button className="button primary" disabled={mutation.isPending || !machineId}>Thêm danh sách</button></div></form></Modal>;
}

function TransferDialog({ account, users, onClose, onSaved }: { account: TikTokAccount; users: User[]; onClose: () => void; onSaved: () => void }) {
  const [ownerId, setOwnerId] = useState(account.owner_id);
  const [machineId, setMachineId] = useState(account.machine_id);
  const [slot, setSlot] = useState(account.slot_number);
  const { data } = useQuery({
    queryKey: ["machines", ownerId],
    queryFn: () => api<{ machines: Machine[] }>(`/api/machines?owner_id=${encodeURIComponent(ownerId)}`),
  });
  const machines = data?.machines || [];
  const mutation = useMutation({
    mutationFn: () => api(`/api/accounts/${account.id}/transfer`, { method: "PATCH", body: JSON.stringify({ machine_id: machineId, slot_number: slot }) }),
    onSuccess: () => { notify("Đã chuyển kênh", "success"); onSaved(); },
    onError: (error) => notify((error as Error).message, "error"),
  });
  return <Modal title={`Chuyển @${account.username}`} onClose={onClose}><form className="form-stack" onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }}><label>Người nhận<select value={ownerId} onChange={(e) => { setOwnerId(e.target.value); setMachineId(""); }}>{users.filter((item) => item.is_active).map((person) => <option key={person.id} value={person.id}>{person.full_name} · {person.role}</option>)}</select></label><label>Máy đích<select value={machineId} required onChange={(e) => setMachineId(e.target.value)}><option value="">Chọn máy</option>{machines.map((machine) => <option key={machine.id} value={machine.id}>Máy #{machine.machine_number} · {machine.account_count}/10 kênh</option>)}</select></label><label>Vị trí kênh<input type="number" min="1" max="10" value={slot} onChange={(e) => setSlot(Number(e.target.value))} required /></label><div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Quay lại</button><button className="button primary" disabled={!machineId || mutation.isPending}>Chuyển kênh</button></div></form></Modal>;
}
