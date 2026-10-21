/** Backend origin for server-side proxies (SSE, etc.). */
export const SPARK_API_URL =
  process.env.SPARK_API_URL ?? process.env.NEXT_PUBLIC_SPARK_API_URL ?? "http://127.0.0.1:8000";
