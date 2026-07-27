import axios, { AxiosError } from "axios";

const SETTINGS_KEY = "NeuralCleave_settings";
const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:7432";

function getApiBase(): string {
  if (typeof window !== "undefined") {
    try {
      const saved = localStorage.getItem(SETTINGS_KEY);
      if (saved) {
        const settings = JSON.parse(saved) as Record<string, Record<string, string>>;
        let url = settings?.api?.["Backend API URL"];
        if (url) {
          // One-time migration: Windows 11 resolves 'localhost' to ::1 (IPv6) before
          // 127.0.0.1 (IPv4). The backend binds to IPv4 only, so WebView2 connections
          // to ::1:7432 hang silently. Rewrite any stored localhost URL to 127.0.0.1.
          if (url.includes("localhost")) {
            url = url.replace("localhost", "127.0.0.1");
            settings.api["Backend API URL"] = url;
            localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
          }
          return url;
        }
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

// Normalize gateway errors into a consistent shape so call sites don't need
// to unwrap raw AxiosError or display raw network error messages.
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (!error.response) {
      // Network-level failure (gateway unreachable, CORS, timeout).
      const gatewayError = new Error(
        "Cannot reach the NeuralCleave gateway. Check that it is running and that " +
          "the Backend API URL in Settings is correct.",
      );
      (gatewayError as Error & { isGatewayError: boolean }).isGatewayError = true;
      return Promise.reject(gatewayError);
    }
    // HTTP error — re-reject as-is so call sites can inspect status codes.
    return Promise.reject(error);
  },
);

export default apiClient;
