import fs from "node:fs";
import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
/** Read SL_BOT_API_TOKEN from backend/.env for dev proxy injection only. */
function readBackendBotToken() {
    var envPath = path.resolve(__dirname, "../backend/.env");
    if (!fs.existsSync(envPath))
        return "";
    var text = fs.readFileSync(envPath, "utf8");
    for (var _i = 0, _a = text.split(/\r?\n/); _i < _a.length; _i++) {
        var line = _a[_i];
        var trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#"))
            continue;
        var eq = trimmed.indexOf("=");
        if (eq < 0)
            continue;
        if (trimmed.slice(0, eq).trim() !== "SL_BOT_API_TOKEN")
            continue;
        return trimmed
            .slice(eq + 1)
            .trim()
            .replace(/^["']|["']$/g, "");
    }
    return "";
}
export default defineConfig(function (_a) {
    var _b;
    var command = _a.command, mode = _a.mode;
    var env = loadEnv(mode, __dirname, "");
    var isBuild = command === "build";
    // The bot token maps straight to tenant 1 with service privileges
    // (core/auth_middleware.py). Anything `define`d here is inlined verbatim into
    // the shipped JS, so baking it into a build publishes an admin credential to
    // every visitor. Dev only: injected by the proxy below, which runs in Node
    // and never reaches the browser.
    var proxyBotToken = isBuild
        ? ""
        : (env.VITE_SL_BOT_TOKEN || readBackendBotToken()).trim();
    if (isBuild && (env.VITE_SL_BOT_TOKEN || "").trim()) {
        throw new Error("VITE_SL_BOT_TOKEN is set during a production build. It would be inlined " +
            "into the bundle in plaintext and is equivalent to an admin credential. " +
            "Unset it and authenticate with a user login instead.");
    }
    return {
        define: proxyBotToken
            ? { "import.meta.env.VITE_SL_BOT_TOKEN": JSON.stringify(proxyBotToken) }
            : {},
        plugins: [
            react(),
            VitePWA({
                registerType: "autoUpdate",
                // Registered by hand in main.tsx so the update path stays visible.
                injectRegister: null,
                includeAssets: ["favicon.svg", "apple-touch-icon-180x180.png"],
                manifest: {
                    name: "SmartLearning · 智能知识管理与面试训练",
                    short_name: "SmartLearning",
                    description: "知识库 · 题库 · 刻意练习 · 待办与复习提醒",
                    lang: "zh-CN",
                    // Phones open this straight to the daily plan; change to "/" for the wiki list.
                    start_url: "/todos",
                    scope: "/",
                    display: "standalone",
                    theme_color: "#0f172a",
                    background_color: "#0f172a",
                    icons: [
                        { src: "/pwa-192x192.png", sizes: "192x192", type: "image/png" },
                        { src: "/pwa-512x512.png", sizes: "512x512", type: "image/png" },
                        {
                            src: "/pwa-maskable-512x512.png",
                            sizes: "512x512",
                            type: "image/png",
                            purpose: "maskable",
                        },
                    ],
                },
                workbox: {
                    globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
                    // highlight.js + react-markdown push the main chunk past the 2 MiB default.
                    maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
                    navigateFallback: "/index.html",
                    // `/api/*` is deliberately left unrouted rather than given a NetworkOnly
                    // rule: an unmatched request never reaches the worker's fetch handler, so
                    // the SSE chat stream keeps flowing untouched. The denylist stops the
                    // navigation fallback from answering API calls with the app shell.
                    navigateFallbackDenylist: [/^\/api\//],
                    cleanupOutdatedCaches: true,
                },
                // A worker in dev would cache Vite's HMR client and fight the dev server.
                devOptions: { enabled: false },
            }),
        ],
        resolve: {
            alias: {
                "@": path.resolve(__dirname, "./src"),
            },
        },
        server: {
            port: 5173,
            proxy: {
                "/api": {
                    target: (_b = process.env.VITE_API_BASE) !== null && _b !== void 0 ? _b : "http://127.0.0.1:8000",
                    changeOrigin: true,
                    configure: proxyBotToken
                        ? function (proxy) {
                            proxy.on("proxyReq", function (proxyReq) {
                                // Do not override user JWT sessions with the dev bot token.
                                if (!proxyReq.getHeader("authorization")) {
                                    proxyReq.setHeader("X-SL-Token", proxyBotToken);
                                }
                            });
                        }
                        : undefined,
                },
            },
        },
    };
});
