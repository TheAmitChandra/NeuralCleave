/** @type {import('next').NextConfig} */
const nextConfig = {
  // "standalone" powers the Docker deploy (frontend/Dockerfile expects
  // .next/standalone). The Tauri desktop shell instead needs a static
  // `out/` folder it can embed directly — no Node server at runtime —
  // so `npm run build:tauri` flips this to "export" via TAURI_BUILD.
  // Never set globally: changing the default here would break the
  // existing Docker image.
  output: process.env.TAURI_BUILD === "true" ? "export" : "standalone",
};

export default nextConfig;
