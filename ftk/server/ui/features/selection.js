// Remembers the last used option selection of every command (per project), so switching
// between commands no longer resets the panel. The helpers are shared with the queue.
const PREFIX = "toolkit-sel:";

export const projectKey = (api) => {
    const cfg = api.getConfig();
    return cfg?.project?.id || cfg?.project_root || "default";
};
const storageKey = (api, cmd) => `${PREFIX}${projectKey(api)}:${cmd}`;
const boxes = (root) => [...root.querySelectorAll('input[type="checkbox"][data-flag]')];
const groupLabel = (el) => el.closest(".group")?.querySelector(".group-label")?.textContent?.trim() ?? "";
const isForm = (cfg) => !!cfg && !cfg.static && !cfg.type;

/** Flags that are on / off (enabled boxes only) plus the value of every select. */
export function captureSnapshot(root) {
    const on = [];
    const off = [];
    for (const cb of boxes(root)) {
        if (!cb.disabled) { (cb.checked ? on : off).push(cb.dataset.flag); }
    }
    const sel = {};
    for (const s of root.querySelectorAll("select:not(:disabled)")) { sel[groupLabel(s)] = s.value; }
    return { on, off, sel };
}

/** Keep what we knew about options that are not in the panel right now (not loaded yet / disabled). */
export function mergeSnapshots(old, cur) {
    if (!old) { return cur; }
    const known = new Set([...cur.on, ...cur.off]);
    return {
        on: [...cur.on, ...(old.on ?? []).filter((f) => !known.has(f))],
        off: [...cur.off, ...(old.off ?? []).filter((f) => !known.has(f))],
        sel: { ...(old.sel ?? {}), ...cur.sel },
    };
}

/**
 * Put a snapshot back into the panel. The core re-runs its constraint / preset sync on every
 * `change`, so we dispatch one and apply again (an option may only become enabled afterwards).
 */
export function applySnapshot(root, snap) {
    if (!snap) { return false; }
    const on = new Set(snap.on ?? []);
    const off = new Set(snap.off ?? []);
    let touched = false;
    for (let pass = 0; pass < 3; pass++) {
        let changed = false;
        for (const cb of boxes(root)) {
            if (cb.disabled) { continue; }
            const want = on.has(cb.dataset.flag) ? true : (off.has(cb.dataset.flag) ? false : null);
            if (want !== null && cb.checked !== want) { cb.checked = want; changed = true; }
        }
        for (const s of root.querySelectorAll("select:not(:disabled)")) {
            const want = snap.sel?.[groupLabel(s)];
            if (want === undefined || s.value === want) { continue; }
            if ([...s.options].some((o) => o.value === want && !o.disabled)) { s.value = want; changed = true; }
        }
        if (!changed) { break; }
        touched = true;
        root.querySelector("input:not(:disabled),select:not(:disabled)")
            ?.dispatchEvent(new Event("change", { bubbles: true }));
    }
    return touched;
}

export function load(api, cmd) {
    try { return JSON.parse(localStorage.getItem(storageKey(api, cmd)) ?? "null"); } catch { return null; }
}

export function save(api, cmd, snap, { replace = false } = {}) {
    try {
        const value = replace ? snap : mergeSnapshots(load(api, cmd), snap);
        localStorage.setItem(storageKey(api, cmd), JSON.stringify(value));
    } catch { /* storage full or disabled: the panel just keeps resetting, as before */ }
}

export function init(api) {
    let restoring = false;
    const restore = (name) => {
        const saved = load(api, name);
        if (!saved) { return; }
        restoring = true;
        try { applySnapshot(api.configEl, saved); } finally { restoring = false; }
    };
    api.bus.on("config:rendered", ({ cmd, name }) => { if (isForm(cmd)) { restore(name); } });
    api.bus.on("config:folders", ({ name }) => { if (name === api.getActiveCmd()) { restore(name); } });
    api.bus.on("preview:sync", () => {
        if (restoring) { return; }
        const name = api.getActiveCmd();
        if (name && isForm(api.getActiveConfig())) { save(api, name, captureSnapshot(api.configEl)); }
    });
}
