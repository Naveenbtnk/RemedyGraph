import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function securityHeaders(development: boolean) {
  const commonHeaders = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
  };
  if (development) {
    return commonHeaders;
  }

  return {
    ...commonHeaders,
    "Content-Security-Policy": [
      "default-src 'self'",
      "base-uri 'self'",
      "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000",
      "font-src 'self'",
      "form-action 'self'",
      "frame-ancestors 'none'",
      "img-src 'self' data:",
      "object-src 'none'",
      "script-src 'self'",
      "style-src 'self'",
    ].join("; "),
  };
}

export default defineConfig({
  plugins: [react()],
  // Vite injects a refresh preamble during development; strict CSP applies to production preview.
  server: { port: 5173, headers: securityHeaders(true) },
  preview: { headers: securityHeaders(false) },
});
