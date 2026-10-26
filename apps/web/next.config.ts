import type { NextConfig } from "next";

/**
 * Same-origin deployment: the browser only ever talks to this origin. Next proxies the
 * dashboard API (including the live SSE stream) and the health probes to the API service,
 * so the httpOnly session cookie stays first-party and no CORS is needed. Agents post to
 * the API directly, never through Next. In production a
 * load balancer may route these paths straight to the API before they reach Next.
 */
const apiInternal = (process.env.API_INTERNAL_URL || "http://localhost:4430").replace(/\/+$/, "");

const prod = process.env.NODE_ENV === "production";

/**
 * Next inlines its bootstrap scripts and styles, so those need 'unsafe-inline'; the dev
 * server also needs 'unsafe-eval' for fast refresh. Everything is loaded from this origin.
 */
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${prod ? "" : " 'unsafe-eval'"}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self'${prod ? "" : " ws:"}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig: NextConfig = {
  // One self-contained server bundle (`node server.js`), the unit a container image ships.
  output: "standalone",
  outputFileTracingRoot: __dirname,
  poweredByHeader: false,
  devIndicators: false,
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiInternal}/api/:path*` },
      { source: "/healthz", destination: `${apiInternal}/healthz` },
      { source: "/readyz", destination: `${apiInternal}/readyz` },
      { source: "/docs", destination: `${apiInternal}/docs` },
      { source: "/openapi.json", destination: `${apiInternal}/openapi.json` },
      { source: "/health", destination: `${apiInternal}/health` },
    ];
  },
  async headers() {
    const common = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
      // Browsers honour HSTS only over HTTPS, so this is inert on http://localhost.
      ...(prod ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }] : []),
    ];
    return [
      { source: "/:path*", headers: common },
      // The dashboard itself: same-origin everything. /docs (Swagger UI from a CDN, served by
      // the API) and /openapi.json keep the API's own headers instead.
      { source: "/((?!docs|openapi\\.json).*)", headers: [{ key: "Content-Security-Policy", value: csp }] },
    ];
  },
};

export default nextConfig;
