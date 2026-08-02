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

export interface VoiceDevice {
  index: number;
  name: string;
  channels: number;
  sample_rate: number;
  is_default: boolean;
}

export interface VoiceDevicesResponse {
  input: VoiceDevice[];
  output: VoiceDevice[];
  active: { input_device: string | null; output_device: string | null };
}

export async function getVoiceDevices(): Promise<VoiceDevicesResponse> {
  const res = await apiClient.get<VoiceDevicesResponse>("/voice/devices");
  return res.data;
}

export default apiClient;

// ─── Voice continuous-listen API ───────────────────────────────────────────────

export interface ContinuousListenStatus {
  continuous_available: boolean;
  continuous_listening: boolean;
}

export async function getContinuousListenStatus(): Promise<ContinuousListenStatus> {
  const { data } = await apiClient.get<ContinuousListenStatus>("/voice/listen/status");
  return data;
}

export async function startContinuousListening(): Promise<{ started: boolean; already_running?: boolean; reason?: string }> {
  const { data } = await apiClient.post<{ started: boolean; already_running?: boolean; reason?: string }>("/voice/listen/start");
  return data;
}

export async function stopContinuousListening(): Promise<{ stopped: boolean; already_stopped?: boolean; reason?: string }> {
  const { data } = await apiClient.post<{ stopped: boolean; already_stopped?: boolean; reason?: string }>("/voice/listen/stop");
  return data;
}

// ─── Voice status (unified snapshot) ──────────────────────────────────────────

export interface VoiceStatusResponse {
  runtime_available: boolean;
  continuous_listening: boolean;
  wake_detector_active: boolean;
  is_handoff_active: boolean;
  ptt_available: boolean;
  ptt_is_recording: boolean;
  stt_available: boolean;
  tts_available: boolean;
}

export async function getVoiceStatus(): Promise<VoiceStatusResponse> {
  const { data } = await apiClient.get<VoiceStatusResponse>("/voice/status");
  return data;
}

// ─── Push-to-talk API ─────────────────────────────────────────────────────────

export async function startPtt(): Promise<{ started: boolean; reason?: string }> {
  const { data } = await apiClient.post<{ started: boolean; reason?: string }>("/voice/ptt/start");
  return data;
}

export async function stopPtt(): Promise<{ transcript?: string; response?: string }> {
  const { data } = await apiClient.post<{ transcript?: string; response?: string }>("/voice/ptt/stop");
  return data;
}
