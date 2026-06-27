import axios from "axios";

// CortexFlow-AI's gateway is a single-user local daemon — no auth, default
// port 7432 (see [gateway] in ~/.cortexflow/config.toml).
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7432";

export const apiClient = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
});

export default apiClient;
