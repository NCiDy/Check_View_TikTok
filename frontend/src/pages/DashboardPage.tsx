import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Clock3, Crown, Radio, ShieldAlert, TrendingUp, UsersRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../AuthContext";
import { useStartCheck } from "../hooks/useStartCheck";
import type { Dashboard } from "../types";
import { formatNumber, formatTime } from "../utils";

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const check = useStartCheck();
  const isCompanyAdmin = user?.role === "BOSS" || user?.role === "MANAGER";
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<Dashboard>("/api/dashboard"),
  });

  const cards = [
    { label: "Tổng kênh", value: data?.total, icon: UsersRound, tone: "blue", filter: "ALL" },
    { label: "Đang LIVE", value: data?.live, icon: CheckCircle2, tone: "green", filter: "LIVE" },
    { label: "Tổng kênh BKT", value: data?.monetized, icon: Crown, tone: "amber", filter: "ALL" },
    { label: "Chờ JOIN", value: data?.join_pending, icon: Clock3, tone: "violet", filter: "ALL" },
    { label: "Kênh to", value: data?.large, icon: TrendingUp, tone: "blue", filter: "ALL" },
    { label: "Chờ duyệt lại", value: data?.review_pending, icon: Radio, tone: "amber", filter: "ALL" },
    { label: "Loại", value: data?.rejected, icon: ShieldAlert, tone: "red", filter: "ALL" },
  ];

  const title = isCompanyAdmin ? "Toàn công ty" : user?.role === "LEADER" ? "Nhóm của bạn" : "Kênh của bạn";

  return (
    <div className="page-stack">
      <div className="page-heading">
        <div><p className="eyebrow">TỔNG QUAN</p><h1>{title}</h1><p>Cập nhật trực tiếp từ Supabase và checker TikTok.</p></div>
        {isCompanyAdmin && (
          <button className="button primary" disabled={check.isPending} onClick={() => {
            if (window.confirm("Bắt đầu check toàn bộ kênh trong công ty?")) check.mutate({ scope_type: "COMPANY" });
          }}><Radio size={17} /> Check toàn công ty</button>
        )}
      </div>

      <section className="metric-grid">
        {cards.map(({ label, value, icon: Icon, tone, filter }) => (
          <button key={label} className={`metric-card tone-${tone}`} onClick={() => navigate(`/accounts?status=${filter}&owner=ALL`)}>
            <span className="metric-icon"><Icon size={20} /></span>
            <span className="metric-label">{label}</span>
            <strong>{isLoading ? "…" : formatNumber(value || 0)}</strong>
          </button>
        ))}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div><p className="eyebrow">THAY ĐỔI GẦN ĐÂY</p><h2>Followers tự động</h2></div>
          <span className="muted">Lần check gần nhất: {formatTime(data?.last_checked_at)}</span>
        </div>
        <div className="change-list">
          {data?.recent_changes?.length ? data.recent_changes.map((item) => (
            <button key={`${item.account_id}-${item.checked_at}`} className="change-row" onClick={() => navigate(`/accounts?owner=${item.owner_id}`)}>
              <span><strong>@{item.username}</strong><small>{item.owner_name} · Máy #{item.machine_number} · Kênh {item.slot_number}</small></span>
              <span className={item.delta >= 0 ? "delta-positive" : "delta-negative"}>
                {formatNumber(item.before)} → {formatNumber(item.after)} ({item.delta > 0 ? "+" : ""}{formatNumber(item.delta)})
              </span>
            </button>
          )) : <div className="empty-state">Chưa có thay đổi followers từ lịch check tự động.</div>}
        </div>
      </section>
    </div>
  );
}
