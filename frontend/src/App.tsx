import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Building2, ClipboardList, KeyRound, LayoutDashboard, LogOut, Menu, Network, RefreshCw, Search, Settings2, Shield, Users, Volume2, VolumeX, X } from "lucide-react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, notify } from "./api";
import { useAuth } from "./AuthContext";
import { Avatar } from "./components/Avatar";
import { JobPanel } from "./components/JobPanel";
import { Modal } from "./components/Modal";
import { ToastViewport } from "./components/ToastViewport";
import { useRealtime } from "./RealtimeContext";
import { AccountsPage } from "./pages/AccountsPage";
import { AuditPage } from "./pages/AuditPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { OrganizationPage } from "./pages/OrganizationPage";
import { PeoplePage } from "./pages/PeoplePage";
import { SessionsPage } from "./pages/SessionsPage";
import { SettingsPage } from "./pages/SettingsPage";
import type { CheckRun, TikTokAccount } from "./types";

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <div className="boot-screen"><span className="brand-mark large">TT</span><p>Đang kết nối hệ thống…</p></div>;
  return <><ToastViewport />{user ? <AuthenticatedApp /> : <LoginPage />}</>;
}

function AuthenticatedApp() {
  const { user, logout, refreshMe } = useAuth();
  const {
    connected,
    setCurrentRun,
    voiceEnabled,
    toggleVoice,
    updateRequired,
  } = useRealtime();
  const queryClient = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const { data: runs } = useQuery({ queryKey: ["current-run"], queryFn: () => api<{ runs: CheckRun[] }>("/api/check-runs/current") });
  useEffect(() => { if (runs?.runs[0]) setCurrentRun(runs.runs[0]); }, [runs, setCurrentRun]);
  useEffect(() => setMobileOpen(false), [location.pathname]);

  const isCompanyAdmin = user?.role === "BOSS" || user?.role === "MANAGER";
  const isSystemAccount = user?.username.toLowerCase() === "system" && user?.is_technical_account;

  const nav = [
    { to: "/", label: "Tổng quan", icon: LayoutDashboard, end: true },
    { to: "/accounts", label: "Kênh TikTok", icon: Activity },
    { to: "/organization", label: "Tổ chức nhân sự", icon: Network },
    ...(isCompanyAdmin ? [
      { to: "/people", label: "Quản lý nhân sự", icon: Users },
      { to: "/audit", label: "Nhật ký", icon: ClipboardList },
      { to: "/settings", label: "Cấu hình", icon: Settings2 },
    ] : []),
    { to: "/sessions", label: "Phiên đăng nhập", icon: Shield },
  ];

  async function uploadOwnAvatar(file?: File) {
    if (!file || !user) return;
    const body = new FormData(); body.append("avatar", file);
    try { await api(`/api/users/${user.id}/avatar`, { method: "POST", body }); await refreshMe(); await queryClient.invalidateQueries({ queryKey: ["users"] }); notify("Đã đổi ảnh đại diện", "success"); } catch (error) { notify((error as Error).message, "error"); }
  }

  async function announceUpdate() {
    const confirmed = window.confirm(
      "Gửi thông báo yêu cầu tải lại trang đến tất cả mọi người đang online?"
    );

    if (!confirmed) return;

    try {
      const result = await api<{
        success: boolean;
        message: string;
      }>("/api/system/announce-update", {
        method: "POST",
      });

      notify(result.message, "success");
    } catch (error) {
      notify((error as Error).message, "error");
    }
  }

  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? "open" : ""}`}>
      <div className="sidebar-brand"><span className="brand-mark">TT</span><div><strong>BEATOK Manager</strong><small>Company Workspace</small></div><button className="mobile-close" onClick={() => setMobileOpen(false)}><X size={20} /></button></div>
      <nav>{nav.map(({ to, label, icon: Icon, end }) => <NavLink key={to} to={to} end={end}><Icon size={18} /><span>{label}</span></NavLink>)}</nav>
      <div className="sidebar-status"><span className={connected ? "connection-dot online" : "connection-dot"} /><div><strong>{connected ? "Đang kết nối" : "Đang kết nối lại"}</strong><small>Realtime WebSocket</small></div></div>
    </aside>
    {mobileOpen && <button className="mobile-overlay" onClick={() => setMobileOpen(false)} />}
    <div className="main-column">
      <header className="topbar"><button className="mobile-menu" onClick={() => setMobileOpen(true)}><Menu size={21} /></button><div className="topbar-context"><Building2 size={18} /><span>Không gian công ty</span></div><div className="topbar-actions">{isCompanyAdmin && <button className="topbar-button" onClick={() => setSearchOpen(true)}><Search size={17} /><span>Tìm toàn công ty</span></button>}{isSystemAccount && (
        <button
          className="topbar-button update-button"
          onClick={() => void announceUpdate()}
          title="Thông báo mọi người tải lại web"
        >
          <RefreshCw size={17} />
          <span>Thông báo cập nhật</span>
        </button>
      )}<button className="topbar-button" onClick={toggleVoice}>{voiceEnabled ? <Volume2 size={17} /> : <VolumeX size={17} />}<span>{voiceEnabled ? "Đang bật loa" : "Bật loa"}</span></button><label className="profile-button" title="Bấm để đổi ảnh"><Avatar name={user!.full_name} url={user!.avatar_url} size="sm" /><span><strong>{user!.full_name}</strong><small>{user!.role}{user!.is_system_owner ? " · Chính" : ""}</small></span><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => void uploadOwnAvatar(e.target.files?.[0])} /></label><button className="icon-button" title="Đổi mật khẩu" onClick={() => setPasswordOpen(true)}><KeyRound size={18} /></button><button className="icon-button logout-icon" title="Đăng xuất" onClick={() => void logout()}><LogOut size={18} /></button></div></header>
      <JobPanel />
      <main className="content"><Routes><Route path="/" element={<DashboardPage />} /><Route path="/accounts" element={<AccountsPage />} /><Route path="/organization" element={<OrganizationPage />} /><Route path="/sessions" element={<SessionsPage />} />{isCompanyAdmin && <><Route path="/people" element={<PeoplePage />} /><Route path="/audit" element={<AuditPage />} /><Route path="/settings" element={<SettingsPage />} /></>}<Route path="*" element={<Navigate to="/" replace />} /></Routes></main>
    </div>
    {searchOpen && <SearchDialog onClose={() => setSearchOpen(false)} onOpenOwner={(id) => { setSearchOpen(false); navigate(`/accounts?owner=${id}`); }} />}
    {passwordOpen && <PasswordDialog onClose={() => setPasswordOpen(false)} />}
    {updateRequired && (
      <div className="update-notice-overlay">
        <div className="update-notice-card">
          <div className="update-notice-icon">
            <RefreshCw size={25} />
          </div>

          <div>
            <strong>Web vừa có bản cập nhật mới</strong>
            <p>
              Vui lòng tải lại trang để sử dụng giao diện và chức năng mới nhất.
            </p>
          </div>

          <button
            type="button"
            className="button primary"
            onClick={() => window.location.reload()}
          >
            Tải lại ngay
          </button>
        </div>
      </div>
    )}
  </div>;
}

function SearchDialog({ onClose, onOpenOwner }: { onClose: () => void; onOpenOwner: (id: string) => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TikTokAccount[]>([]);
  const [loading, setLoading] = useState(false);
  return <Modal title="Tìm username toàn công ty" onClose={onClose}><form className="search-dialog" onSubmit={async (e) => { e.preventDefault(); setLoading(true); try { const data = await api<{ results: TikTokAccount[] }>(`/api/search?q=${encodeURIComponent(query)}`); setResults(data.results); } catch (error) { notify((error as Error).message, "error"); } finally { setLoading(false); } }}><label className="search-box"><Search size={17} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="@username" autoFocus required /></label><button className="button primary" disabled={loading}>Tìm</button></form><div className="search-results">{results.map((item) => <button key={item.id} onClick={() => onOpenOwner(item.owner_id)}><span><strong>@{item.username}</strong><small>{item.owner_name} · Máy #{item.machine_number}, kênh {item.slot_number}</small></span><span>{item.status}</span></button>)}</div></Modal>;
}

function PasswordDialog({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState(""); const [next, setNext] = useState(""); const [loading, setLoading] = useState(false);
  return <Modal title="Đổi mật khẩu" onClose={onClose}><form className="form-stack" onSubmit={async (e) => { e.preventDefault(); setLoading(true); try { await api("/api/auth/change-password", { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) }); notify("Đã đổi mật khẩu", "success"); onClose(); } catch (error) { notify((error as Error).message, "error"); } finally { setLoading(false); } }}><label>Mật khẩu hiện tại<input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required autoFocus /></label><label>Mật khẩu mới<input type="password" minLength={8} value={next} onChange={(e) => setNext(e.target.value)} required /></label><div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Hủy</button><button className="button primary" disabled={loading}>Đổi mật khẩu</button></div></form></Modal>;
}
