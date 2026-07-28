import type { NextConfig } from "next";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [new URL("http://localhost:8001/api/books/**")],
  },
  turbopack: {
    root: appRoot,
  },
};

export default nextConfig;
