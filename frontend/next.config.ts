import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",
  reactStrictMode: true,
  outputFileTracingRoot: path.join(__dirname),
};

export default nextConfig;
