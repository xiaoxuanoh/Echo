import type { NextConfig } from "next";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = dirname(fileURLToPath(import.meta.url));
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";
const apiUrl = new URL(apiBaseUrl);

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: apiUrl.protocol.replace(":", "") as "http" | "https",
        hostname: apiUrl.hostname,
        port: apiUrl.port,
        pathname: "/api/books/**",
      },
    ],
  },
  turbopack: {
    root: appRoot,
  },
};

export default nextConfig;
