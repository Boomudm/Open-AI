/** @type {import('next').NextConfig} */
const isProd = process.env.NODE_ENV === "production";

function sparkApiProxyTarget() {
  const raw =
    [
      process.env.SPARK_API_PROXY_TARGET,
      process.env.SPARK_API_URL,
      process.env.NEXT_PUBLIC_SPARK_API_URL,
    ].find((value) => value?.trim()) ?? "http://127.0.0.1:8000";
  return raw.replace(/\/$/, "");
}

const nextConfig = {
  ...(isProd ? { output: "standalone" } : {}),
  webpack: (config) => {
    config.resolve.alias.canvas = false;
    return config;
  },
  async redirects() {
    const toChat = [
      "/rag-chat",
      "/alerts",
      "/optimization",
      "/jobs",
    ];
    const toUpload = ["/ingest"];
    // /repairs and /inventory were removed — repair history now lives on /dashboard.
    const toDashboard = ["/analytics", "/repair-history", "/repairs", "/inventory"];
    return [
      ...toDashboard.flatMap((source) => [
        { source, destination: "/dashboard", permanent: false },
        { source: `${source}/:path*`, destination: "/dashboard", permanent: false },
      ]),
      ...toChat.flatMap((source) => [
        { source, destination: "/chat", permanent: false },
        { source: `${source}/:path*`, destination: "/chat", permanent: false },
      ]),
      ...toUpload.flatMap((source) => [
        { source, destination: "/upload", permanent: false },
        { source: `${source}/:path*`, destination: "/upload", permanent: false },
      ]),
    ];
  },
  async rewrites() {
    const base = sparkApiProxyTarget();
    return [{ source: "/api/:path*", destination: `${base}/api/:path*` }];
  },
  // Chat answers stream over SSE through this rewrite proxy — the default
  // 30s proxyTimeout can kill long answers before backend budgets expire.
  experimental: {
    optimizePackageImports: ["lucide-react"],
    proxyTimeout: 300_000,
  },
};

export default nextConfig;
