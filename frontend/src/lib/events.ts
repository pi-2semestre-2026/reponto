import { API_URL, setToken } from "./api";
import { getToken } from "./token";

/** Subscribe to committed database changes; return cleanup for React effects. */
export function subscribeEvents(onChange: () => Promise<void>) {
  let stopped = false;
  let controller: AbortController | undefined;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let refreshing = false;
  let pending = false;

  const refresh = async () => {
    pending = true;
    if (refreshing || stopped || document.hidden) return;
    refreshing = true;
    try {
      while (pending && !stopped && !document.hidden) {
        pending = false;
        await onChange();
      }
    } finally { refreshing = false; }
  };

  const connect = async () => {
    const token = getToken();
    if (stopped || controller || !token) return;
    const connection = new AbortController();
    controller = connection;
    try {
      const response = await fetch(`${API_URL}/events`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: connection.signal,
        cache: "no-store",
      });
      if (response.status === 401) {
        if (!stopped && getToken() === token) {
          stopped = true;
          setToken(null);
          window.location.href = "/login";
        }
        return;
      }
      if (!response.ok || !response.body) throw new Error("Events unavailable");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      try {
        while (!stopped && getToken() === token) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let end: number;
          while ((end = buffer.indexOf("\n\n")) !== -1) {
            const frame = buffer.slice(0, end);
            buffer = buffer.slice(end + 2);
            if (/^event: (ready|change)$/m.test(frame)) void refresh();
          }
        }
      } finally {
        await reader.cancel().catch(() => {});
        reader.releaseLock();
      }
    } catch {
      // Retry the event connection, without periodically fetching sales.
    } finally {
      if (controller === connection) controller = undefined;
      if (!stopped && !connection.signal.aborted) retry = setTimeout(connect, 3000);
    }
  };

  const visible = () => { if (!document.hidden) void refresh(); };
  const online = () => {
    clearTimeout(retry);
    controller?.abort();
    controller = undefined;
    void connect();
  };
  document.addEventListener("visibilitychange", visible);
  window.addEventListener("online", online);
  void connect();
  return () => {
    stopped = true;
    clearTimeout(retry);
    controller?.abort();
    document.removeEventListener("visibilitychange", visible);
    window.removeEventListener("online", online);
  };
}
