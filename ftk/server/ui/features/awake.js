// "Keep awake" button in the header. The server holds the OS-level request (see
// ftk/server/keepawake.py); this just switches it and shows the state:
//   off -> until the run finishes -> always on -> off
// While it is active the browser's Screen Wake Lock is requested too (best effort, only
// works in a secure context and while the tab is visible).
const ENDPOINT = "/api/keepawake";
const TITLES = {
    off: "Keep awake: OFF\nClick to keep this machine awake until the current / next run finishes",
    run: "Keep awake: until the run finishes\nClick again to keep it awake until you turn it off",
    on: "Keep awake: ON until you turn it off\nClick to turn it off",
};

async function call(method, body) {
    const opts = { method };
    if (body) { 
        opts.headers = { "Content-Type": "application/json" }; 
        opts.body = JSON.stringify(body); 
    }
    const res = await fetch(ENDPOINT, opts);
    if (!res.ok) { throw new Error(`HTTP ${res.status}`); }
    return res.json();
}

export function init(api) {
    const btn = api.$("awake-btn");
    if (!btn) { return; }
    let state = { supported: false, active: false, auto_off: false, backend: "", error: "" };
    let busy = false;
    let lock = null;
    const lockApi = typeof navigator !== "undefined" && "wakeLock" in navigator;

    const mode = () => {
        if (!state.active) {
            return "off";
        }
        return state.auto_off ? "run" : "on";
    };

    function render() {
        const m = mode();
        const unavailable = !state.supported && !state.active;
        btn.hidden = false;
        btn.dataset.mode = m;
        btn.disabled = unavailable;
        btn.classList.toggle("pending", busy);
        btn.setAttribute("aria-pressed", String(m !== "off"));
        let title = unavailable ? "Keep awake is not available here (the server found no OS support for it)" : TITLES[m];
        if (state.error) { title += `\n⚠ ${state.error}`; }
        btn.title = title;
    }

    async function syncLock() {
        if (!lockApi) { return; }
        const want = state.active && document.visibilityState === "visible";
        if (want && !lock) {
            try {
                lock = await navigator.wakeLock.request("screen");
                lock.addEventListener("release", () => { lock = null; });
            } catch { lock = null; }
        } else if (!want && lock) {
            try { await lock.release(); } catch { /* already released */ }
            lock = null;
        }
    }

    async function refresh(userAction = false) {
        const was = state.active;
        try { state = await call("GET"); }
        catch { state = { ...state, error: "Server not reachable" }; }
        if (was && !state.active && !userAction) {
            api.appendLine("☕ Keep awake released (the run finished)", "line-info");
        }
        await syncLock();
        render();
    }

    async function toggle() {
        if (busy) { return; }
        const m = mode();
        let body;
        if (m === "off") {
            body = { enabled: true, auto_off: true };
        } else if (m === "run") {
            body = { enabled: true, auto_off: false };
        } else {
            body = { enabled: false };
        }
        busy = true;
        render();
        try { state = await call("POST", body); }
        catch { state = { ...state, error: "Server not reachable" }; }
        busy = false;
        await syncLock();
        render();
    }

    btn.addEventListener("click", toggle);
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") { refresh(true); } });
    api.bus.on("ws:open", () => refresh(true));
    api.bus.on("ws:msg", (msg) => {
        if (msg.type === "exit" || msg.type === "stopped" || msg.type === "error") { setTimeout(() => refresh(false), 400); }
    });
    render();
    refresh(true);
}
