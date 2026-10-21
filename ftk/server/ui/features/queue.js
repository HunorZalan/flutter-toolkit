// Queue: chain several commands and run them one after another (see ftk/pipeline.py).
// The list is built from the normal command panels with the "+" button next to Run and is
// kept per project in localStorage. Running it is a single, ordinary run of the "queue"
// command, so it survives a closed tab; this file only follows its progress markers.
import { captureSnapshot, projectKey, save as saveSelection } from "./selection.js";

const SEP = "+";
const STORE = "toolkit-queue:";
const NOT_QUEUEABLE = new Set(["queue", "notes", "help", "run"]);
// Progress lines printed by `ftk pipeline`. The leading symbols are not matched on purpose:
// a legacy console encoding may mangle them.
const RE_BANNER = /^=== Step (\d+)\/(\d+): /;
const RE_OK = /Step (\d+)\/(\d+) finished \(exit 0, ([\d.]+)s\)/;
const RE_FAIL = /Step (\d+)\/(\d+) failed \(exit (-?\d+), ([\d.]+)s\)/;
const RE_SKIP = /Step (\d+)\/(\d+) skipped/;
const STATE_TEXT = {
    pending: "waiting", running: "running…", ok: "done", fail: "failed",
    skipped: "skipped", stopped: "stopped", lost: "connection lost",
};

function h(tag, props = {}, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
        if (k === "class") { el.className = v; }
        else if (k === "text") { el.textContent = v; }
        else if (k.startsWith("on")) { el.addEventListener(k.slice(2), v); }
        else if (v === true) { el.setAttribute(k, ""); }
        else if (v !== false && v != null) { el.setAttribute(k, v); }
    }
    el.append(...kids.flat().filter(Boolean));
    return el;
}

const quote = (t) => {
    const safePattern = /^[\w@%+=:,./-]+$/;
    if (safePattern.test(t)) {
        return t;
    }
    const escaped = t.replaceAll(/(["\\$`])/g, String.raw`\$1`);
    return `"${escaped}"`;
};
const uid = () => crypto.randomUUID();

/** Human readable labels of whatever is selected in the option panel. */
function describe(root) {
    const labels = [];
    let excludes = 0;
    for (const cb of root.querySelectorAll('input[type="checkbox"]:checked:not(:disabled)')) {
        const flag = cb.dataset.flag || "";
        if (flag.startsWith("--exclude ")) { excludes++; continue; }
        const text = cb.closest(".opt-row")?.querySelector(".label-text")?.textContent?.trim();
        if (text) { labels.push(text); }
    }
    for (const sel of root.querySelectorAll("select:not(:disabled)")) {
        const text = sel.value && sel.selectedOptions[0]?.textContent?.trim();
        if (text) { labels.push(text); }
    }
    if (excludes) { labels.push(`Exclude ×${excludes}`); }
    return labels;
}

export function init(api) {
    const { bus, $ } = api;
    const addBtn = $("btn-queue-add");
    const countEl = $("queue-count");
    const baseTitle = () => document.querySelector(".header h1")?.textContent?.trim() || "Flutter Toolkit";

    let steps = [];
    let keepGoing = false;
    let run = null; // { active, ids, status: Map, info: Map, note }
    let panel = null;

    const meta = (name) => api.getConfig()?.commands?.[name];
    const queueable = (name) => {
        const m = meta(name);
        return !!m && !!m.script && !m.static && !m.type && !m.disabled && !NOT_QUEUEABLE.has(name);
    };
    const hasFlag = (name, flag) => !!meta(name)?.groups?.some((g) => g.options?.some((o) => o.flag === flag && !o.disabled));
    const runnable = () => steps.filter((s) => s.enabled && queueable(s.cmd));
    const locked = () => !!run?.active;
    const busyNow = () => !api.isConnected() || api.isRunning();
    const stepArgs = (s, dry) => (dry && hasFlag(s.cmd, "--dry-run") && !s.args.includes("--dry-run")
        ? [...s.args, "--dry-run"] : s.args);

    function queueArgs(list, dry) {
        const argv = keepGoing ? ["--keep-going"] : [];
        list.forEach((s, i) => {
            if (i) { argv.push(SEP); }
            argv.push(s.cmd, ...stepArgs(s, dry));
        });
        return argv;
    }

    // ---- persistence (per project) ----
    const key = () => `${STORE}${projectKey(api)}`;
    function load() {
        steps = [];
        try {
            const data = JSON.parse(localStorage.getItem(key()) ?? "null");
            keepGoing = !!data?.keepGoing;
            for (const s of Array.isArray(data?.steps) ? data.steps : []) {
                if (!s || typeof s.cmd !== "string" || !Array.isArray(s.args)) { continue; }
                steps.push({
                    id: s.id || uid(), cmd: s.cmd, title: s.title || s.cmd, args: s.args.map(String),
                    labels: Array.isArray(s.labels) ? s.labels : [], snap: s.snap ?? null, enabled: s.enabled !== false,
                });
            }
        } catch { steps = []; }
    }
    function save() {
        try {
            localStorage.setItem(key(), JSON.stringify({
                v: 1, keepGoing,
                steps: steps.map(({ id, cmd, title, args, labels, snap, enabled }) => ({ id, cmd, title, args, labels, snap, enabled })),
            }));
        } catch { /* storage full or disabled */ }
    }

    // ---- the "+" button next to Run ----
    function updateAdd() {
        if (!addBtn) { return; }
        const name = api.getActiveCmd();
        addBtn.disabled = !queueable(name);
        addBtn.title = queueable(name)
            ? `Add "${meta(name).title}" with the current options to the queue`
            : "Open a command and set its options to add it to the queue";
    }
    function badge() {
        const n = runnable().length;
        if (countEl) { countEl.textContent = String(n); countEl.hidden = n === 0; }
    }
    function addStep() {
        const name = api.getActiveCmd();
        if (!queueable(name)) { return; }
        steps.push({
            id: uid(), cmd: name, title: meta(name).title, args: api.buildArgs(),
            labels: describe(api.configEl), snap: captureSnapshot(api.configEl), enabled: true,
        });
        save(); badge(); draw();
        addBtn.classList.add("pulse");
        setTimeout(() => addBtn.classList.remove("pulse"), 700);
    }

    // ---- editing ----
    const mutate = (fn) => { fn(); save(); badge(); draw(); };
    const move = (i, d) => mutate(() => { const j = i + d; if (j >= 0 && j < steps.length) { [steps[i], steps[j]] = [steps[j], steps[i]]; } });
    const dup = (i) => mutate(() => { steps.splice(i + 1, 0, { ...steps[i], id: uid(), args: [...steps[i].args], labels: [...steps[i].labels] }); });
    const remove = (i) => mutate(() => { steps.splice(i, 1); });
    function edit(s) {
        // The command panel restores its saved selection when it opens, so hand it this step's.
        if (s.snap) { saveSelection(api, s.cmd, s.snap, { replace: true }); }
        api.selectCmd(s.cmd);
    }

    // ---- running ----
    function confirmRun(dry) {
        const list = runnable();
        if (!list.length || busyNow() || locked()) { return; }
        api.askConfirm({
            title: dry ? "Dry run the queue" : "Run the queue",
            message: `${list.length} step(s) in this order. ${keepGoing ? "Continues after a failure." : "Stops at the first failure."}`,
            preview: list.map((s, i) => `${i + 1}. ${[s.cmd, ...stepArgs(s, dry)].join(" ")}`).join("\n"),
            okLabel: "Run (Enter)", cancelLabel: "Cancel (ESC)",
            onOk: () => startRun(list, dry),
        });
    }
    function startRun(list, dry) {
        if (busyNow()) { return; }
        run = { active: true, ids: list.map((s) => s.id), status: new Map(list.map((s) => [s.id, "pending"])), info: new Map(), note: "" };
        draw();
        try { api.executeRun("queue", queueArgs(list, dry)); }
        catch (err) { finish("error", String(err?.message ?? err)); }
    }
    function confirmClear() {
        if (!steps.length || locked()) { return; }
        api.askConfirm({
            title: "Clear the queue", message: `Remove all ${steps.length} step(s)?`,
            okLabel: "Clear (Enter)", cancelLabel: "Cancel (ESC)",
            onOk: () => mutate(() => { steps = []; run = null; }),
        });
    }
    async function copyCli(button) {
        const list = runnable();
        if (!list.length) { return; }
        const text = ["ftk", "pipeline", ...queueArgs(list, false).map(quote)].join(" ");
        const before = button.textContent;
        try { await navigator.clipboard.writeText(text); button.textContent = "Copied!"; }
        catch { button.textContent = "Copy failed"; }
        setTimeout(() => { button.textContent = before; }, 1500);
    }

    // ---- following the run ----
    const setState = (id, state, detail) => {
        if (!id) { return; }
        run.status.set(id, state);
        if (detail) { run.info.set(id, detail); }
        setTimeout(draw, 0);
    };
    function onLine(text) {
        const at = (n) => run.ids[Number(n) - 1];
        let m = RE_BANNER.exec(text);
        if (m) {
            setState(at(m[1]), "running");
            const s = steps.find((x) => x.id === at(m[1]));
            document.title = `▶ ${m[1]}/${m[2]} ${s?.cmd ?? ""} – ${baseTitle()}`;
            return;
        }
        m = RE_OK.exec(text);
        if (m) {
            setState(at(m[1]), "ok", `${m[3]}s`);
            return;
        }
        m = RE_FAIL.exec(text);
        if (m) {
            setState(at(m[1]), "fail", `exit ${m[3]} · ${m[4]}s`);
            return;
        }
        m = RE_SKIP.exec(text);
        if (m) {
            setState(at(m[1]), "skipped");
        }
    }
    function finish(kind, detail = "") {
        if (!run?.active) { return; }
        run.active = false;
        for (const id of run.ids) {
            const st = run.status.get(id);
            if (st === "running") {
                let statusValue = "fail";
                if (kind === "stopped") {
                    statusValue = "stopped";
                } else if (kind === "lost") {
                    statusValue = "lost";
                }
                run.status.set(id, statusValue);
            }
            else if (st === "pending") { run.status.set(id, "skipped"); }
        }
        run.note = {
            done: "finished", failed: keepGoing ? "finished with failures" : "stopped at a failure",
            stopped: "stopped by you", lost: "connection lost – the server may still be running it",
            error: detail || "could not start",
        }[kind] ?? "";
        setTimeout(draw, 0); // after the core has processed the same message
    }
    bus.on("ws:msg", (msg) => {
        if (!run?.active) { return; }
        if (msg.type === "output") { onLine(String(msg.data ?? "")); }
        else if (msg.type === "exit") { finish(msg.code === 0 ? "done" : "failed"); }
        else if (msg.type === "stopped") { finish("stopped"); }
        else if (msg.type === "error") { finish("error", String(msg.data ?? "")); }
    });
    bus.on("ws:close", () => finish("lost"));
    bus.on("ws:open", () => setTimeout(draw, 0));

    // ---- the Queue panel ----
    function draw() {
        if (!panel?.isConnected) { return; }
        panel.replaceChildren(toolbar(), summary(), steps.length ? list() : h("p", {
            class: "queue-empty",
            text: "The queue is empty. Open a command, set its options and press the + button next to Run.",
        }));
    }
    function toolbar() {
        const n = runnable().length;
        const idle = !busyNow() && !locked();
        return h("div", { class: "queue-toolbar" },
            h("button", { type: "button", class: "btn btn-run", disabled: !n || !idle, onclick: () => confirmRun(false), title: "Run the queue" }, "▶ Run queue"),
            h("button", { type: "button", class: "btn btn-clear", disabled: !n || !idle, onclick: () => confirmRun(true), title: "Run every step with --dry-run where the command supports it" }, "Dry run"),
            h("label", { class: "queue-opt", title: "Carry on with the next step even if one fails" },
                h("input", { type: "checkbox", checked: keepGoing, disabled: locked(), onchange: (e) => { keepGoing = e.target.checked; save(); } }),
                "Keep going after a failure"),
            h("span", { class: "grow" }),
            h("button", { type: "button", class: "btn btn-clear", disabled: !n, onclick: (e) => copyCli(e.currentTarget), title: "Copy the equivalent command line" }, "Copy CLI"),
            h("button", { type: "button", class: "btn btn-clear", disabled: !steps.length || !idle, onclick: confirmClear, title: "Remove every step" }, "Clear"));
    }
    function summary() {
        let text = steps.length ? `${runnable().length} of ${steps.length} step(s) will run` : "";
        if (run && !run.active && run.note) { text += `${text ? " – " : ""}last run: ${run.note}`; }
        return h("p", { class: "queue-summary", text });
    }
    const iconBtn = (glyph, title, disabled, fn) => h("button", { type: "button", class: "qs-btn", title, "aria-label": title, disabled, onclick: fn, text: glyph });
    function renderStep(s, i, frozen) {
        const st = run?.status.get(s.id);
        const info = run?.info.get(s.id);
        const ok = queueable(s.cmd);
        const mayPrompt = hasFlag(s.cmd, "--yes") && !s.args.includes("--yes");

        return h("li", { class: ["queue-step", s.enabled ? "" : "off", st ? `status-${st}` : "", ok ? "" : "missing"].filter(Boolean).join(" "), "data-id": s.id },
            h("input", { type: "checkbox", class: "qs-on", checked: s.enabled, disabled: frozen, title: "Include this step", onchange: (e) => mutate(() => { s.enabled = e.target.checked; }) }),
            h("div", { class: "qs-main" },
                h("div", { class: "qs-head" },
                    h("span", { class: "qs-num", text: String(i + 1) }),
                    h("span", { class: "qs-title", text: s.title }),
                    st ? h("span", { class: "qs-state", text: STATE_TEXT[st] + (info ? ` · ${info}` : "") }) : null,
                    ok ? null : h("span", { class: "qs-state", text: "unavailable" })),
                h("div", { class: "queue-chips" },
                    ...(s.labels.length ? s.labels : ["defaults"]).map((l) => h("span", { class: "queue-chip", text: l })),
                    mayPrompt ? h("span", { class: "queue-chip warn", title: "Without --yes this step may stop and wait for your answer", text: "may prompt" }) : null),
                h("code", { class: "qs-cli", text: [s.cmd, ...s.args].join(" ") })),
            h("div", { class: "qs-actions" },
                iconBtn("↑", "Move up", frozen || i === 0, () => move(i, -1)),
                iconBtn("↓", "Move down", frozen || i === steps.length - 1, () => move(i, 1)),
                iconBtn("⧉", "Duplicate", frozen, () => dup(i)),
                iconBtn("✎", "Load these options into the command panel", frozen || !ok, () => edit(s)),
                iconBtn("✕", "Remove", frozen, () => remove(i)))
        );
    }
    function list() {
        const frozen = locked();
        return h("ol", { class: "queue-list" }, ...steps.map((s, i) => renderStep(s, i, frozen)));
    }
    api.registerPanel("queue", (_cmd, _name, root) => {
        panel = h("div", { class: "queue-panel" });
        root.appendChild(panel);
        draw();
    });
    if (addBtn) { addBtn.hidden = false; addBtn.addEventListener("click", addStep); }
    const refresh = () => { updateAdd(); badge(); };
    bus.on("config:loaded", () => { load(); refresh(); draw(); });
    bus.on("cmd:selected", refresh);
    bus.on("config:rendered", updateAdd);
    if (api.getConfig()) { load(); refresh(); }
}
