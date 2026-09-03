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
    onError: (error) => notify((error as Error).message, "error"),
  });
}
