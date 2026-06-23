/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emit a self-contained server bundle (.next/standalone) for the production
  // Docker image — see frontend/Dockerfile. No other behavior changes.
  output: "standalone",
};

export default nextConfig;
