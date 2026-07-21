/**
 * api.js  –  Shared HTTP + auth helpers for all AFID portals.
 * Include this file BEFORE any portal-specific scripts:
 *   <script src="api.js"></script>
 */

const BASE_URL = "http://127.0.0.1:8000";   // change to your server address if needed

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
