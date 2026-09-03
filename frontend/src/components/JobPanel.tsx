import { Square } from "lucide-react";
import { api, notify } from "../api";
import { useRealtime } from "../RealtimeContext";

export function JobPanel() {
  const { currentRun, setCurrentRun } = useRealtime();
  if (!currentRun) return null;
  const done = ["COMPLETED", "STOPPED", "FAILED"].includes(currentRun.status);
  const progress = currentRun.progress_percent || 0;

  async function stop() {
    try {
      await api(`/api/check-runs/${currentRun?.id}/stop`, { method: "POST" });
      notify("Đã gửi yêu cầu dừng job", "success");
    } catch (error) {
      notify((error as Error).message, "error");
    }
  }

  return (
    <aside className="job-panel">
      <div className="job-topline">
        <div>
          <strong>{currentRun.trigger_type === "SCHEDULED" ? "Check tự động" : "Job của bạn"}</strong>
          <span className={`status-dot status-${currentRun.status.toLowerCase()}`}>{currentRun.status}</span>
        </div>
        {done ? (
          <button className="link-button" onClick={() => setCurrentRun(null)}>Đóng</button>
        ) : (
          <button className="button danger small" onClick={stop}><Square size={14} /> Dừng</button>
        )}
      </div>
      <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
      <div className="job-meta">
        <span>{currentRun.processed_accounts || 0}/{currentRun.total_accounts}</span>
        <span>LIVE {currentRun.live_count || 0}</span>
        <span>DIE {currentRun.die_count || 0}</span>
        <span>ERROR {currentRun.error_count || 0}</span>
      </div>
    </aside>
  );
}
