import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { notify } from "./api";
import { useAuth } from "./AuthContext";
import type { CheckRun } from "./types";

interface RealtimeState {
  connected: boolean;
  currentRun: CheckRun | null;
  setCurrentRun: (run: CheckRun | null) => void;
  voiceEnabled: boolean;
  toggleVoice: () => void;
}

const RealtimeContext = createContext<RealtimeState | null>(null);

function speak(message: string) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const speech = new SpeechSynthesisUtterance(message);
  speech.lang = "vi-VN";
  speech.rate = 1;
  window.speechSynthesis.speak(speech);
}

export function RealtimeProvider({ children }: { children: React.ReactNode }) {
  const { user, sessionId, refreshMe, forceSignOut } = useAuth();
  const userId = user?.id;
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [currentRun, setCurrentRun] = useState<CheckRun | null>(null);
  const [voiceEnabled, setVoiceEnabled] = useState(localStorage.getItem("tiktokSpeechEnabled") === "1");
  const reconnectTimer = useRef<number | null>(null);

  const refreshSharedData = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["accounts"] });
    void queryClient.invalidateQueries({ queryKey: ["machines"] });
    void queryClient.invalidateQueries({ queryKey: ["users"] });
    void queryClient.invalidateQueries({ queryKey: ["organization"] });
  }, [queryClient]);

  useEffect(() => {
    if (!userId || !sessionId) return;
    let disposed = false;
    let socket: WebSocket | null = null;
    let pingTimer: number | null = null;

    const connect = () => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${location.host}/ws`);
      socket.onopen = () => {
        setConnected(true);
        pingTimer = window.setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send("ping"), 60_000);
      };
      socket.onmessage = (event) => {
        let message: { type: string; data: Record<string, unknown> };
        try { message = JSON.parse(event.data); } catch { return; }
        const data = message.data || {};

        if (message.type === "connected") {
          void refreshMe();
          refreshSharedData();
        }

        if (["job_started", "job_progress", "job_finished", "job_failed"].includes(message.type)) {
          const run = data.run as unknown as CheckRun | undefined;
          if (run && (!run.requested_session_id || run.requested_session_id === sessionId || run.trigger_type === "SCHEDULED")) {
            setCurrentRun(run);
            if (message.type === "job_finished") notify("Job check đã hoàn thành", "success");
            if (message.type === "job_failed") notify(run.message || "Job check thất bại", "error");
          }
        }
        if (message.type === "data_updated") refreshSharedData();
        if (message.type === "directory_updated") {
          refreshSharedData();
          if (data.user_id === userId) void refreshMe();
        }
        if (message.type === "permissions_updated") {
          void refreshMe();
          refreshSharedData();
          notify("Quyền tài khoản vừa được cập nhật", "info");
        }
        if (message.type === "settings_updated") {
          void queryClient.invalidateQueries({ queryKey: ["settings"] });
        }
        if (message.type === "session_revoked") {
          forceSignOut(String(data.reason || "Phiên đăng nhập đã bị thu hồi"));
          socket?.close();
        }
        if (message.type === "alert") {
          const alertMessage = String(data.message || "Có thay đổi mới");
          notify(alertMessage, data.type === "STATUS_CHANGE" ? "error" : "success");
          if (voiceEnabled && data.voice_enabled) speak(alertMessage);
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (pingTimer) window.clearInterval(pingTimer);
        if (!disposed) reconnectTimer.current = window.setTimeout(connect, 3000);
      };
    };
    connect();
    return () => {
      disposed = true;
      if (pingTimer) window.clearInterval(pingTimer);
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
      socket?.close();
    };
  }, [forceSignOut, queryClient, refreshMe, refreshSharedData, sessionId, userId, voiceEnabled]);

  const toggleVoice = useCallback(() => {
    setVoiceEnabled((value) => {
      const next = !value;
      localStorage.setItem("tiktokSpeechEnabled", next ? "1" : "0");
      if (next) speak("Đã bật đọc thông báo");
      return next;
    });
  }, []);

  const value = useMemo(() => ({ connected, currentRun, setCurrentRun, voiceEnabled, toggleVoice }), [connected, currentRun, voiceEnabled, toggleVoice]);
  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtime() {
  const value = useContext(RealtimeContext);
  if (!value) throw new Error("useRealtime phải nằm trong RealtimeProvider");
  return value;
}
