/**
 * api.js  –  Shared HTTP + auth helpers for all AFID portals.
 * Include this file BEFORE any portal-specific scripts:
 *   <script src="api.js"></script>
 */

// Same-origin: API calls go to the host serving these pages, which forwards
// them to the backend — via the Vite dev proxy locally, and via the Vercel
// rewrite in production (see vercel.json). No hard-coded backend URL, no CORS.
//
// Everything is funnelled through a single "/api" prefix so the proxy rule is
// always "/api/:path*", i.e. it ALWAYS matches at least one path segment.
//
// The previous setup mapped each resource prefix separately ("/doctors/:path*",
// "/presets/:path*", …). Those patterns matched a bare "/doctors" with ZERO
// segments, and in that case Vercel answers with a 307 REDIRECT to the backend
// (over http://, no less) instead of proxying. Browsers strip the Authorization
// header on a cross-origin redirect, so those calls arrived unauthenticated and
// came back 401 — which the handler below then read as an expired session and
// used to wipe the user's login. Symptomatically: "no doctor accounts found",
// an empty doctor matrix, and random logouts.
const BASE_URL = "/api";

// ── Token / User storage ──────────────────────────────────────────────────────
function getToken()        { return localStorage.getItem("afid_token"); }
function setToken(t)       { localStorage.setItem("afid_token", t); }
function removeToken()     { localStorage.removeItem("afid_token"); }

function getUser()         { try { return JSON.parse(localStorage.getItem("afid_user")); } catch { return null; } }
function setUser(u)        { localStorage.setItem("afid_user", JSON.stringify(u)); }
function removeUser()      { localStorage.removeItem("afid_user"); }

// ── Core request helper ───────────────────────────────────────────────────────
/**
 * @param {string} path   – e.g. "/auth/login"
 * @param {RequestInit} options – fetch options (method, body, headers, …)
 * @returns {Promise<any>} parsed JSON response
 * @throws  {Error}  with a human-readable message on HTTP errors
 */
async function apiRequest(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };

    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

    if (res.status === 204) return null;          // No Content

    let data;
    try { data = await res.json(); } catch { data = {}; }

    if (!res.ok) {
        // Handle 401 Unauthorized - token expired or invalid.
        //
        // Only treat this as an EXPIRED SESSION when the request actually
        // carried a token. A 401 from /auth/login just means the credentials
        // were wrong: bouncing to Login.html in that case reloaded the page out
        // from under the error banner, so a mistyped password produced a silent
        // refresh and no explanation at all -- which is indistinguishable from
        // "this account doesn't work".
        const isAuthAttempt = path.startsWith("/auth/login") || path.startsWith("/auth/register");
        if (res.status === 401 && token && !isAuthAttempt) {
            // Clear auth data and redirect to login
            removeToken();
            removeUser();
            window.location.replace("Login.html");
            throw new Error("Session expired. Please log in again.");
        }

        // FastAPI validation errors come in data.detail (array or string)
        const detail = Array.isArray(data.detail)
            ? data.detail.map(e => e.msg).join(", ")
            : (data.detail || `HTTP ${res.status}`);
        throw new Error(detail);
    }
    return data;
}

// ── Convenience wrappers ──────────────────────────────────────────────────────
const api = {
    get:    (path)         => apiRequest(path),
    post:   (path, body)   => apiRequest(path, { method: "POST",   body: JSON.stringify(body) }),
    put:    (path, body)   => apiRequest(path, { method: "PUT",    body: JSON.stringify(body) }),
    patch:  (path, body)   => apiRequest(path, { method: "PATCH",  body: JSON.stringify(body) }),
    delete: (path)         => apiRequest(path, { method: "DELETE" }),
};

// ── Branded dialogs ───────────────────────────────────────────────────────────
/**
 * In-page replacements for window.alert / confirm / prompt.
 *
 * The native dialogs render the browser chrome's origin line -- "localhost:5173
 * says…" locally, and the deployment hostname in production -- which looks
 * like a browser warning rather than part of the application. These render
 * inside the page instead, so no origin is ever shown.
 *
 * All three are async: `await uiAlert(...)`, `if (await uiConfirm(...))`,
 * `const v = await uiPrompt(...)` (uiPrompt resolves to null when cancelled).
 */
(function installDialogs() {
    const STYLE_ID = "afid-dialog-styles";

    function ensureStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
      .afid-dlg-backdrop {
        position: fixed; inset: 0; background: rgba(5, 51, 33, 0.55);
        display: flex; align-items: center; justify-content: center;
        z-index: 100000; padding: 20px; animation: afidDlgFade .15s ease-out;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      }
      @keyframes afidDlgFade { from { opacity: 0 } to { opacity: 1 } }
      .afid-dlg {
        background: #fff; border-radius: 14px; width: 100%; max-width: 440px;
        box-shadow: 0 24px 48px rgba(3, 37, 26, .28); overflow: hidden;
      }
      .afid-dlg-head {
        background: #0b4c33; color: #fff; padding: 16px 22px;
        font-size: 14px; font-weight: 800; letter-spacing: .3px;
      }
      .afid-dlg-head.is-warn { background: #b45309; }
      .afid-dlg-head.is-error { background: #991b1b; }
      .afid-dlg-body {
        padding: 22px; font-size: 14px; line-height: 1.55; color: #1f2937;
        white-space: pre-wrap; word-break: break-word;
      }
      .afid-dlg-body input {
        width: 100%; margin-top: 14px; padding: 10px 14px; font-size: 14px;
        border: 1px solid #cbd5e1; border-radius: 6px; color: #1f2937;
        background: #fff; box-sizing: border-box;
      }
      .afid-dlg-body input:focus { outline: none; border-color: #0b4c33; box-shadow: 0 0 0 3px rgba(11,76,51,.15); }
      .afid-dlg-foot {
        display: flex; justify-content: flex-end; gap: 10px;
        padding: 0 22px 20px 22px;
      }
      .afid-dlg-btn {
        border: none; border-radius: 7px; padding: 10px 20px; cursor: pointer;
        font-size: 13px; font-weight: 700; font-family: inherit;
      }
      .afid-dlg-btn.primary { background: #0b4c33; color: #fff; }
      .afid-dlg-btn.primary:hover { background: #106b47; }
      .afid-dlg-btn.ghost { background: #fff; color: #4b5563; border: 1px solid #cbd5e1; }
      .afid-dlg-btn.ghost:hover { background: #f9fafb; }
    `;
        document.head.appendChild(style);
    }

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function open({ title, message, tone, mode, defaultValue, confirmLabel, cancelLabel }) {
        ensureStyles();
        return new Promise(resolve => {
            const backdrop = document.createElement("div");
            backdrop.className = "afid-dlg-backdrop";
            const toneClass = tone === "error" ? " is-error" : tone === "warn" ? " is-warn" : "";
            backdrop.innerHTML = `
        <div class="afid-dlg" role="dialog" aria-modal="true">
          <div class="afid-dlg-head${toneClass}">${escapeHtml(title)}</div>
          <div class="afid-dlg-body">${escapeHtml(message)}${
                mode === "prompt" ? `<input type="text" class="afid-dlg-input" value="${escapeHtml(defaultValue || "")}" />` : ""
            }</div>
          <div class="afid-dlg-foot">
            ${mode === "alert" ? "" : `<button type="button" class="afid-dlg-btn ghost" data-act="cancel">${escapeHtml(cancelLabel || "Cancel")}</button>`}
            <button type="button" class="afid-dlg-btn primary" data-act="ok">${escapeHtml(confirmLabel || "OK")}</button>
          </div>
        </div>`;

            const input = backdrop.querySelector(".afid-dlg-input");

            function close(result) {
                document.removeEventListener("keydown", onKey, true);
                backdrop.remove();
                resolve(result);
            }
            function accept() {
                if (mode === "prompt") return close(input ? input.value : "");
                close(mode === "confirm" ? true : undefined);
            }
            function reject() {
                close(mode === "prompt" ? null : mode === "confirm" ? false : undefined);
            }
            function onKey(e) {
                if (e.key === "Escape") { e.preventDefault(); reject(); }
                else if (e.key === "Enter" && mode !== "alert") { e.preventDefault(); accept(); }
            }

            backdrop.querySelector('[data-act="ok"]').addEventListener("click", accept);
            const cancelBtn = backdrop.querySelector('[data-act="cancel"]');
            if (cancelBtn) cancelBtn.addEventListener("click", reject);
            backdrop.addEventListener("click", e => { if (e.target === backdrop) reject(); });
            document.addEventListener("keydown", onKey, true);

            document.body.appendChild(backdrop);
            if (input) { input.focus(); input.select(); }
            else backdrop.querySelector('[data-act="ok"]').focus();
        });
    }

    window.uiAlert = (message, opts = {}) => open({
        title: opts.title || "AFID HMS",
        message, tone: opts.tone, mode: "alert",
        confirmLabel: opts.confirmLabel || "OK",
    });

    window.uiError = (message, opts = {}) => open({
        title: opts.title || "Action Failed",
        message, tone: "error", mode: "alert",
        confirmLabel: opts.confirmLabel || "Dismiss",
    });

    window.uiConfirm = (message, opts = {}) => open({
        title: opts.title || "Please Confirm",
        message, tone: opts.tone || "warn", mode: "confirm",
        confirmLabel: opts.confirmLabel || "Confirm",
        cancelLabel: opts.cancelLabel || "Cancel",
    });

    window.uiPrompt = (message, opts = {}) => open({
        title: opts.title || "AFID HMS",
        message, mode: "prompt",
        defaultValue: opts.defaultValue || "",
        confirmLabel: opts.confirmLabel || "Save",
        cancelLabel: opts.cancelLabel || "Cancel",
    });
})();

// ── Logout helper ─────────────────────────────────────────────────────────────
async function logout() {
    try {
        // Call backend logout endpoint to trigger patient queue export
        const token = getToken();
        if (token) {
            await apiRequest("/auth/logout", { 
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${token}`
                }
            });
        }
    } catch (error) {
        // Log the error but continue with logout
        console.warn("Backend logout failed, proceeding with client-side logout:", error);
    } finally {
        // Always clear local storage and redirect
        removeToken();
        removeUser();
        window.location.replace("Login.html");
    }
}
