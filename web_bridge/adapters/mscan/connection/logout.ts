import { getAccessToken } from "@/utils/authToken";

/** Capture the current credential before MSCAN clears it or leaves for CAS. */
export function revokeAssistant() {
  const token = getAccessToken();
  void fetch(((import.meta.env.VITE_API_URL as string) || "") + "/cncb/assistant/logout", {
    method: "POST",
    credentials: "same-origin",
    keepalive: true,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) },
    body: "{}"
  }).catch(() => undefined);
}
