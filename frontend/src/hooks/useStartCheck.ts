import { useMutation } from "@tanstack/react-query";
import { api, notify } from "../api";
import { useRealtime } from "../RealtimeContext";
import type { CheckRun } from "../types";

export function useStartCheck() {
  const { setCurrentRun } = useRealtime();
  return useMutation({
    mutationFn: (payload: { scope_type: string; target_user_id?: string | null; account_ids?: string[] }) =>
      api<{ run: CheckRun }>("/api/check-runs", {
        method: "POST",
        body: JSON.stringify({ target_user_id: null, account_ids: [], ...payload }),
      }),
    onSuccess: ({ run }) => {
      setCurrentRun(run);
      notify("Đã bắt đầu job check", "success");
    },
    onError: (error) => {
      notify((error as Error).message, "error");
      // If another session of the same login owns the active job, display it
      // instead of leaving the user with an unexplained blocking toast.
      void api<{ runs: CheckRun[] }>("/api/check-runs/current")
        .then(({ runs }) => { if (runs[0]) setCurrentRun(runs[0]); })
        .catch(() => {});
    },
  });
}
