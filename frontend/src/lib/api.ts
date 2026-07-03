import axios from "axios";

const SETTINGS_KEY = "cortexflow_settings";
const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7432";

function getApiBase(): string {
  if (typeof window !== "undefined") {
    try {
      const saved = localStorage.getItem(SETTINGS_KEY);
      if (saved) {
        const settings = JSON.parse(saved) as Record<string, Record<string, string>>;
        const url = settings?.api?.["Backend API URL"];
        if (url) return url;
      }
    } catch {}
  }
  return DEFAULT_API_BASE;
}

export const apiClient = axios.create({
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
});

// Re-read localStorage on every request so Settings changes take effect immediately.
apiClient.interceptors.request.use((config) => {
  config.baseURL = `${getApiBase()}/api/v1`;
  return config;
});

export default apiClient;
