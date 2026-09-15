import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Clock3, Crown, Radio, ShieldAlert, TrendingUp, Trophy, UsersRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../AuthContext";
import { useStartCheck } from "../hooks/useStartCheck";
import type { Dashboard } from "../types";
import { formatNumber, formatTime } from "../utils";

const COMPOSITION_COLORS = {
  monetized: "#f7c843",
  join_pending: "#8b7cf6",
  large: "#29c5eb",
  review_pending: "#ff922e",
  rejected: "#ff5f73",
  remaining: "#42698f",
};

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
    { label: "Tổng kênh", value: data?.total, icon: UsersRound, tone: "blue", href: "/accounts?owner=ALL&status=ALL" },
    { label: "Đang LIVE", value: data?.live, icon: CheckCircle2, tone: "green", href: "/accounts?owner=ALL&status=LIVE" },
    { label: "Tổng kênh BKT", value: data?.monetized, icon: Crown, tone: "amber", href: "/accounts?owner=ALL&status=ALL&metric=MONETIZED" },
    { label: "Chờ JOIN", value: data?.join_pending, icon: Clock3, tone: "violet", href: "/accounts?owner=ALL&status=ALL&metric=JOIN_PENDING" },
    { label: "Kênh to", value: data?.large, icon: TrendingUp, tone: "blue", href: "/accounts?owner=ALL&status=ALL&metric=LARGE" },
    { label: "Chờ duyệt lại", value: data?.review_pending, icon: Radio, tone: "amber", href: "/accounts?owner=ALL&status=ALL&metric=REVIEW_PENDING" },
    { label: "Loại", value: data?.rejected, icon: ShieldAlert, tone: "red", href: "/accounts?owner=ALL&status=ALL&metric=REJECTED" },
  ];

  const compositionItems = useMemo(() => {
    const composition = data?.composition;
    return [
      { key: "monetized", label: "Tổng kênh BKT", value: composition?.monetized || 0, color: COMPOSITION_COLORS.monetized, href: "/accounts?owner=ALL&status=ALL&metric=MONETIZED" },
      { key: "join_pending", label: "Chờ JOIN", value: composition?.join_pending || 0, color: COMPOSITION_COLORS.join_pending, href: "/accounts?owner=ALL&status=ALL&metric=JOIN_PENDING" },
      { key: "large", label: "Kênh to", value: composition?.large || 0, color: COMPOSITION_COLORS.large, href: "/accounts?owner=ALL&status=ALL&metric=LARGE" },
      { key: "review_pending", label: "Chờ duyệt lại", value: composition?.review_pending || 0, color: COMPOSITION_COLORS.review_pending, href: "/accounts?owner=ALL&status=ALL&metric=REVIEW_PENDING" },
      { key: "rejected", label: "Loại", value: composition?.rejected || 0, color: COMPOSITION_COLORS.rejected, href: "/accounts?owner=ALL&status=ALL&metric=REJECTED" },
      { key: "remaining", label: "Còn lại", value: composition?.remaining || 0, color: COMPOSITION_COLORS.remaining, href: "/accounts?owner=ALL&status=ALL" },
    ];
  }, [data?.composition]);

  const compositionTotal = compositionItems.reduce((total, item) => total + item.value, 0);
  let compositionCursor = 0;
  const donutSegments = compositionItems.map((item) => {
    const start = compositionCursor;
    const size = compositionTotal ? (item.value / compositionTotal) * 100 : 0;
    compositionCursor += size;
    return `${item.color} ${start}% ${compositionCursor}%`;
  });
  const donutBackground = compositionTotal
    ? `conic-gradient(${donutSegments.join(", ")})`
    : "conic-gradient(#24384d 0 100%)";

  const breakthroughs = data?.breakthrough_channels || [];
  const maximumDelta = Math.max(...breakthroughs.map((item) => item.delta), 1);
  const standoutOwner = useMemo(() => {
    const counts = new Map<string, { name: string; count: number }>();
    breakthroughs.forEach((item) => {
      const current = counts.get(item.owner_id);
      counts.set(item.owner_id, {
        name: item.owner_name,
        count: (current?.count || 0) + 1,
      });
    });
    return [...counts.values()].sort((first, second) => second.count - first.count)[0];
  }, [breakthroughs]);

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
        {cards.map(({ label, value, icon: Icon, tone, href }) => (
          <button key={label} className={`metric-card tone-${tone}`} onClick={() => navigate(href)}>
            <span className="metric-icon"><Icon size={20} /></span>
            <span className="metric-label">{label}</span>
            <strong>{isLoading ? "…" : formatNumber(value || 0)}</strong>
          </button>
        ))}
      </section>

      <section className="dashboard-analytics">
        <article className="panel breakthrough-panel">
          <div className="analytics-heading">
            <div>
              <p className="eyebrow">KÊNH BỨT PHÁ</p>
              <h2>Top 5 kênh tăng follow(Toàn Công Ty)</h2>
              <small>So với lần check gần nhất · {formatTime(data?.last_checked_at)}</small>
            </div>
            {standoutOwner && (
              <span className="standout-owner"><Trophy size={15} /> {standoutOwner.name} · {standoutOwner.count}/5 kênh</span>
            )}
          </div>

          <div className="breakthrough-list">
            {breakthroughs.length ? breakthroughs.map((item, index) => (
              <button
                key={item.account_id}
                className="breakthrough-row"
                onClick={() => {
                  if (item.can_open) {
                    navigate(`/accounts?owner=${item.owner_id}&status=ALL`);
                  }
                }}
                disabled={!item.can_open}
              >
                <span className={`breakthrough-rank rank-${index + 1}`}>{index + 1}</span>
                <span className="breakthrough-account">
                  <strong>@{item.username}</strong>
                  <small>{item.owner_name} · Máy #{item.machine_number} · Kênh {item.slot_number}</small>
                </span>
                <span className="breakthrough-progress">
                  <span className="breakthrough-values">{formatNumber(item.before)} → {formatNumber(item.after)}</span>
                  <span className="breakthrough-track"><i style={{ width: `${Math.max(8, (item.delta / maximumDelta) * 100)}%` }} /></span>
                </span>
                <strong className="breakthrough-delta">+{formatNumber(item.delta)}</strong>
              </button>
            )) : (
              <div className="analytics-empty">Chưa có kênh tăng follow sau lần check gần nhất.</div>
            )}
          </div>
        </article>

        <article className="panel composition-panel">
          <div className="analytics-heading">
            <div><p className="eyebrow">CƠ CẤU KÊNH HIỆN TẠI</p><h2>{title}</h2></div>
          </div>
          <div className="composition-content">
            <div className="donut-chart" style={{ background: donutBackground }}>
              <div><strong>{formatNumber(compositionTotal)}</strong><span>Tổng kênh</span></div>
            </div>
            <div className="composition-legend">
              {compositionItems.map((item) => (
                <button key={item.key} onClick={() => navigate(item.href)}>
                  <i style={{ background: item.color }} />
                  <span><strong>{item.label}</strong><small>{formatNumber(item.value)} · {compositionTotal ? ((item.value / compositionTotal) * 100).toFixed(1) : "0.0"}%</small></span>
                </button>
              ))}
            </div>
          </div>
        </article>
      </section>
    </div>
  );
}
