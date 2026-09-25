import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, notify } from "./api";
import { useAuth } from "./AuthContext";
import type { CheckRun, TikTokAccount } from "./types";

interface RealtimeState {
  connected: boolean;
  updateRequired: boolean;
  updateMessage: string | null;
  currentRun: CheckRun | null;
  setCurrentRun: (run: CheckRun | null) => void;
  voiceEnabled: boolean;
  toggleVoice: () => void;
}

interface RealtimeMessage {
  type: string;
  data?: Record<string, unknown>;
}

const RealtimeContext =
  createContext<RealtimeState | null>(null);

function speak(message: string) {
  if (!("speechSynthesis" in window)) return;

  const speech = new SpeechSynthesisUtterance(message);
  speech.lang = "vi-VN";
  speech.rate = 1;

  window.speechSynthesis.speak(speech);
}

export function RealtimeProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const {
    user,
    sessionId,
    refreshMe,
    forceSignOut,
  } = useAuth();

  const userId = user?.id;
  const queryClient = useQueryClient();

  const [connected, setConnected] = useState(false);
  const [updateRequired, setUpdateRequired] = useState(false);
  const [updateMessage, setUpdateMessage] = useState<string | null>(null);
  const [currentRun, setCurrentRun] =
    useState<CheckRun | null>(null);

  const [voiceEnabled, setVoiceEnabled] = useState(
    localStorage.getItem("tiktokSpeechEnabled") === "1"
  );

  const voiceEnabledRef = useRef(voiceEnabled);
  const refreshTimerRef = useRef<number | null>(null);
  const refreshSourcesRef = useRef<Set<string>>(new Set());
  const refreshOwnersRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    voiceEnabledRef.current = voiceEnabled;
  }, [voiceEnabled]);

  const refreshSharedData = useCallback((source = "all", ownerId = "") => {
    // Gộp nhiều sự kiện realtime liên tiếp và chỉ tải lại nhóm dữ liệu
    // thực sự bị ảnh hưởng, tránh tạo một đợt request cho toàn hệ thống.
    refreshSourcesRef.current.add(source);
    if (ownerId) refreshOwnersRef.current.add(ownerId);
    if (refreshTimerRef.current !== null) return;

    refreshTimerRef.current = window.setTimeout(() => {
      refreshTimerRef.current = null;

      const sources = new Set(refreshSourcesRef.current);
      refreshSourcesRef.current.clear();
      const owners = new Set(refreshOwnersRef.current);
      refreshOwnersRef.current.clear();

      const accountOnly = [...sources].every((item) =>
        ["account_condition", "check_run", "account_patch", "dashboard_only"].includes(item)
      );

      void queryClient.invalidateQueries({
        queryKey: ["dashboard"],
      });

      void queryClient.invalidateQueries({ queryKey: ["account-summary"] });

      void queryClient.invalidateQueries({
        refetchType: [...sources].every((item) => ["account_patch", "dashboard_only"].includes(item)) ? "none" : "active",
        predicate: (query) => {
          if (sources.size === 1 && sources.has("dashboard_only")) return false;
          if (query.queryKey[0] !== "accounts") return false;
          if (!owners.size) return true;
          const viewedOwner = String(query.queryKey[1] || "");
          return viewedOwner === "ALL" || owners.has(viewedOwner);
        },
      });

      if (!accountOnly) {
        void queryClient.invalidateQueries({
          predicate: (query) => {
            if (query.queryKey[0] !== "machines") return false;
            if (!owners.size) return true;
            return owners.has(String(query.queryKey[1] || ""));
          },
        });

        void queryClient.invalidateQueries({
          queryKey: ["users"],
        });

        void queryClient.invalidateQueries({
          queryKey: ["organization"],
        });

        void queryClient.invalidateQueries({
          queryKey: ["departments"],
        });
      }
    }, 8_000 + Math.floor(Math.random() * 4_000));
  }, [queryClient]);

  useEffect(() => {
    if (!userId || !sessionId) return;

    let disposed = false;
    let socket: WebSocket | null = null;
    let pingTimer: number | null = null;
    let reconnectTimer: number | null = null;
    let reconnectAttempt = 0;
    let wasConnected = false;

    function clearPingTimer() {
      if (pingTimer !== null) {
        window.clearTimeout(pingTimer);
        pingTimer = null;
      }
    }

    function clearReconnectTimer() {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    }

    function schedulePing() {
      clearPingTimer();

      // Mỗi máy ping lệch nhau từ 45–75 giây.
      const delay =
        45_000 + Math.floor(Math.random() * 30_000);

      pingTimer = window.setTimeout(() => {
        if (
          !disposed &&
          socket?.readyState === WebSocket.OPEN
        ) {
          socket.send("ping");
          schedulePing();
        }
      }, delay);
    }

    function scheduleReconnect() {
      if (disposed || reconnectTimer !== null) return;

      // 1s → 2s → 4s → 8s → tối đa 30s.
      const baseDelay = Math.min(
        30_000,
        1_000 * 2 ** reconnectAttempt
      );

      const jitter = Math.floor(Math.random() * 1_000);

      reconnectAttempt += 1;

      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, baseDelay + jitter);
    }

    function connect() {
      if (disposed) return;

      if (
        socket?.readyState === WebSocket.OPEN ||
        socket?.readyState === WebSocket.CONNECTING
      ) {
        return;
      }

      const scheme =
        location.protocol === "https:" ? "wss" : "ws";

      socket = new WebSocket(
        `${scheme}://${location.host}/ws`
      );

      socket.onopen = () => {
        reconnectAttempt = 0;
        setConnected(true);
        schedulePing();
      };

      socket.onmessage = (event) => {
        let message: RealtimeMessage;

        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }

        const data = message.data || {};

        if (message.type === "connected") {
          void refreshMe();
          if (wasConnected) refreshSharedData("reconnect");
          wasConnected = true;
          void api<{ runs: CheckRun[] }>("/api/check-runs/current").then(({ runs }) => {
            if (!disposed && runs?.length) setCurrentRun(runs[0]);
          }).catch(() => {});
        }

        if (
          [
            "job_started",
            "job_progress",
            "job_finished",
            "job_failed",
          ].includes(message.type)
        ) {
          const run = data.run as
            | CheckRun
            | undefined;

          const belongsToCurrentSession =
            run &&
            (
              !run.requested_session_id ||
              run.requested_session_id === sessionId ||
              run.trigger_type === "SCHEDULED"
            );

          if (run && belongsToCurrentSession) {
            setCurrentRun(run);

            if (message.type === "job_finished") {
              notify(
                run.message || (run.status === "STOPPED" ? "Đã dừng lượt check" : "Đã xử lý đủ số kênh"),
                run.status === "STOPPED" || run.error_count ? "info" : "success"
              );
            }

            if (message.type === "job_failed") {
              notify(
                run.message || "Job check thất bại",
                "error"
              );
            }
          }
        }

        if (message.type === "account_updated") {
          const patch = data.account as Partial<TikTokAccount> | undefined;
          if (patch?.id) {
            queryClient.setQueriesData<{ accounts: TikTokAccount[] }>({ queryKey: ["accounts"] }, (old) =>
              old ? { ...old, accounts: old.accounts.map((account) => {
                if (account.id !== patch.id) return account;
                if (account.last_checked_at && patch.last_checked_at &&
                    Date.parse(account.last_checked_at) > Date.parse(patch.last_checked_at)) return account;
                return { ...account, ...patch };
              }) } : old);
            void queryClient.invalidateQueries({ queryKey: ["account-detail", patch.id] });
            refreshSharedData("account_patch", patch.owner_id || "");
          }
        }
        if (message.type === "dashboard_changed") refreshSharedData("dashboard_only");

        if (message.type === "data_updated") {
          refreshSharedData(
            String(data.source || "all"),
            String(data.owner_id || "")
          );
        }

        if (message.type === "directory_updated") {
          refreshSharedData("directory");

          if (data.user_id === userId) {
            void refreshMe();
          }
        }

        if (message.type === "permissions_updated") {
          void refreshMe();
          refreshSharedData("permissions");

          notify(
            "Quyền tài khoản vừa được cập nhật",
            "info"
          );
        }

        if (message.type === "settings_updated") {
          void queryClient.invalidateQueries({
            queryKey: ["settings"],
          });
        }
        if (message.type === "client_update_required") {
          const customMessage = String(data.custom_message || "").trim();
          setUpdateMessage(customMessage || null);
          setUpdateRequired(true);
        }

        if (message.type === "session_revoked") {
          disposed = true;

          forceSignOut(
            String(
              data.reason ||
                "Phiên đăng nhập đã bị thu hồi"
            )
          );

          socket?.close();
        }

        if (message.type === "alert") {
          const alertMessage = String(
            data.message || "Có thay đổi mới"
          );

          notify(
            alertMessage,
            data.type === "STATUS_CHANGE"
              ? "error"
              : "success"
          );

          if (
            voiceEnabledRef.current &&
            data.voice_enabled
          ) {
            speak(alertMessage);
          }
        }
      };

      socket.onerror = () => {
        socket?.close();
      };

      socket.onclose = (event) => {
        setConnected(false);
        clearPingTimer();
        socket = null;

        // 4401 là phiên hết hạn, không reconnect.
        if (event.code === 4401) {
          disposed = true;

          forceSignOut(
            "Phiên đăng nhập đã hết hạn"
          );

          return;
        }

        scheduleReconnect();
      };
    }

    connect();

    return () => {
      disposed = true;

      clearPingTimer();
      clearReconnectTimer();

      socket?.close(1000, "Component unmounted");
      socket = null;
      setConnected(false);
    };
  }, [
    forceSignOut,
    queryClient,
    refreshMe,
    refreshSharedData,
    sessionId,
    userId,
  ]);

  useEffect(() => {
    return () => {
      if (refreshTimerRef.current !== null) {
        window.clearTimeout(refreshTimerRef.current);
      }
    };
  }, []);

  const toggleVoice = useCallback(() => {
    setVoiceEnabled((currentValue) => {
      const next = !currentValue;

      voiceEnabledRef.current = next;

      localStorage.setItem(
        "tiktokSpeechEnabled",
        next ? "1" : "0"
      );

      if (next) {
        speak("Đã bật đọc thông báo");
      }

      return next;
    });
  }, []);

  const value = useMemo(
    () => ({
      connected,
      currentRun,
      setCurrentRun,
      voiceEnabled,
      toggleVoice,
      updateRequired,
      updateMessage,
    }),
    [
      connected,
      currentRun,
      voiceEnabled,
      toggleVoice,
      updateRequired,
      updateMessage,
    ]
  );

  return (
    <RealtimeContext.Provider value={value}>
      {children}
    </RealtimeContext.Provider>
  );
}

export function useRealtime() {
  const value = useContext(RealtimeContext);

  if (!value) {
    throw new Error(
      "useRealtime phải nằm trong RealtimeProvider"
    );
  }

  return value;
}
