import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Settings2 } from "lucide-react";
import { api, notify } from "../api";
import type { AppSettings } from "../types";
import { formatTime } from "../utils";

export function SettingsPage() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["settings"], queryFn: () => api<{ settings: AppSettings }>("/api/settings") });
  const [form, setForm] = useState<Partial<AppSettings>>({});
  useEffect(() => { if (data?.settings) setForm(data.settings); }, [data]);
  const update = (key: keyof AppSettings, value: number | boolean) => setForm((old) => ({ ...old, [key]: value }));
  const save = useMutation({
    mutationFn: () => api<{ message: string }>("/api/settings", { method: "PATCH", body: JSON.stringify(form) }),
    onSuccess: (result) => { notify(result.message, "success"); void queryClient.invalidateQueries({ queryKey: ["settings"] }); },
    onError: (error) => notify((error as Error).message, "error"),
  });
  if (!data) return <div className="panel empty-state">Đang tải cấu hình…</div>;
  const numberField = (key: keyof AppSettings, label: string, min: number, max?: number, step?: number) => <label>{label}<input type="number" min={min} max={max} step={step} value={Number(form[key] ?? 0)} onChange={(e) => update(key, Number(e.target.value))} /></label>;
  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">HỆ THỐNG</p><h1>Cấu hình checker</h1><p>Giới hạn tài nguyên chung cho tất cả job đang chạy.</p></div><span className="heading-symbol"><Settings2 size={24} /></span></div><form className="panel settings-form" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}><div className="settings-grid">{numberField("check_interval_minutes", "Chu kỳ tự động (phút)", 15, 1440)}{numberField("follower_change_threshold", "Ngưỡng thay đổi follow", 1)}{numberField("max_total_workers", "Tổng worker", 1, 50)}{numberField("max_workers_per_job", "Worker mỗi job", 1, 20)}{numberField("request_timeout_seconds", "Timeout (giây)", 3, 120)}{numberField("retry_count", "Retry lỗi mạng", 0, 5)}{numberField("dead_confirmation_attempts", "Số lần xác nhận DIE", 2, 5)}{numberField("request_delay_seconds", "Delay request (giây)", 0, 60, .1)}</div><div className="checkbox-grid settings-checks"><label><input type="checkbox" checked={Boolean(form.auto_check_enabled)} onChange={(e) => update("auto_check_enabled", e.target.checked)} /> Bật check toàn công ty tự động</label><label><input type="checkbox" checked={Boolean(form.in_app_notifications_enabled)} onChange={(e) => update("in_app_notifications_enabled", e.target.checked)} /> Thông báo trong web</label><label><input type="checkbox" checked={Boolean(form.voice_notifications_enabled)} onChange={(e) => update("voice_notifications_enabled", e.target.checked)} /> Cho phép đọc loa</label></div><div className="settings-footer"><span>Múi giờ: {form.timezone} · Lần chạy kế: {formatTime(form.next_auto_check_at)}</span><button className="button primary" disabled={save.isPending}>Lưu cấu hình</button></div></form></div>;
}
