import type { NextConfig } from "next";

// URL backend — dibaca server-side (untuk rewrites proxy)
// Di Docker, nilai ini diisi via BACKEND_URL (bukan NEXT_PUBLIC_ karena server-side only)
// Di dev lokal, default ke localhost:8001
const API = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

const nextConfig: NextConfig = {
  // Standalone mode: diperlukan untuk Docker (output minimal server)
  output: "standalone",

  // Izinkan <img> dari CDN TikTok tanpa optimisasi Next (avatar profil)
  images: { unoptimized: true },

  // Proxy /api/* ke backend FastAPI → tidak butuh CORS, hanya port 3000 yang exposed
  // Di Docker: Next.js server (dalam container) → backend:8001 via internal network
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },

  // Turbopack root (dev only)
  turbopack: { root: "." },
};

export default nextConfig;
