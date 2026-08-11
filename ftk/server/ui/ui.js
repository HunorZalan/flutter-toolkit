!function () {
    // DOM refs
    const $ = (id) => document.getElementById(id);
    // Layout
    const sidebarEl = $("sidebar");
    const sidebarCollapseBtn = $("sidebar-collapse-btn");
    const logoBtn = $("logo");
    const navEl = $("nav-commands");
    const configEl = $("config");
    const ctrlEl = $("controls");
    const collapseConfigBtn = $("btn-collapse-cfg");
    const collapseOutBtn = $("btn-collapse-out");
    const prevEl = $("preview");
    const outEl = $("output");
    const spinnerEl = $("spinner");
    // Header
    const themeBtn = $("theme-btn");
    const wsDot = $("ws-dot");
    const meta = $("meta-text");
    const footerEl = $("footer-copy");
    // Action buttons
    const runBtn = $("btn-run");
    const stopBtn = $("btn-stop");
    const clearBtn = $("btn-clear");
    const copyBtn = $("btn-copy");
    const undoBtn = $("btn-undo");
    const exportBtn = $("btn-export");
    const autoClearBtn = $("btn-autoclear");
    const scrollTopBtn = $("btn-scroll-top");
    const scrollBotBtn = $("btn-scroll-bot");
    const filterBar = $("filter-bar");
    const filterToggleBtn = $("btn-filter");
    const soundBtn = $("btn-sound");
    // Search
    const searchToggleBtn = $("btn-search");
    const searchBar = $("search-bar");
    const searchInput = $("search-input");
    const searchCount = $("search-count");
    const searchPrev = $("search-prev");
    const searchNext = $("search-next");
    const searchClose = $("search-close");
    // Confirm dialog
    const confirmDialog = $("confirm-dialog");
    const confirmMsg = $("confirm-msg");
    const confirmPreview = $("confirm-preview");
    const confirmOk = $("confirm-ok");
    const confirmCancel = $("confirm-cancel");
    // Status bar
    const sbLines = $("sb-lines");
    const sbCmd = $("sb-cmd");
    const sbResult = $("sb-result");
    const sbDuration = $("sb-duration");
    const sbProgress = $("sb-progress");
    const sbTime = $("sb-time");
    // Constants
    const BASE_TITLE = document.querySelector(".header h1")?.textContent?.trim() || "Flutter Toolkit";
    const welcomeHTML = configEl.innerHTML;
    const MAX_OUTPUT_LINES = 50000;
    // Platform
    const isMac = /Macintosh|Mac OS X/i.test(navigator.userAgent);
    const ctrlLabel = isMac ? '⌘' : 'Ctrl';
    const altLabel = isMac ? '⌥' : 'Alt';
    const kbd = s => s.replace(/\bCtrl\b/g, ctrlLabel).replace(/\bAlt\b/g, altLabel);
    // Apply to all initial [title] attrs + welcome shortcut spans (before welcomeHTML snapshot)
    if (isMac) {
        document.querySelectorAll('[title]').forEach(el => { el.title = kbd(el.title); });
        document.querySelectorAll('.shortcuts span').forEach(el => { el.textContent = kbd(el.textContent); });
    }
    // State
    let ws = null;
    let config = null;
    let activeConfig = null;
    let activeCmd = null;
    let runningCmd = null;
    let running = false;
    let autoScroll = true;
    let lastClearedOutput = null;
    let lastClearedBadges = null;
    let runTimer = null;
    let runStart = 0;
    let clockTimer = null;
    let filterVisible = false;
    let audioCtx = null;
    let lastClearedStatusBar = null;
    let activeFilter = "all";
    let autoClearEnabled = localStorage.getItem("toolkit-autoclear") === "1";
    let soundEnabled = localStorage.getItem("toolkit-sound") !== "0";
    let shortcutsCollapsed = localStorage.getItem("toolkit-shortcuts-collapsed") !== "0";
    const cmdLineCounts = {};
    // Flag tooltips
    const FLAG_TIPS = {
        "--kill": "Finds and kills all running dart/flutter processes.",
        "--clean": "Runs `flutter clean` and deletes pubspec.lock.",
        "--build-cache": "Deletes the build/ and .dart_tool/ directories.",
        "--android": "Runs gradlew clean and clears the Gradle cache.",
        "--ios": "Runs pod deintegrate and clears derived data (macOS only).",
        "--get": "Runs `flutter pub get` to restore dependencies.",
        "--upgrade": "Runs `flutter pub upgrade --major-versions`.",
        "--pub-cache": "Clears the global pub cache (`flutter pub cache clean`).",
        "--flutter-upgrade": "Upgrades the Flutter SDK (`flutter upgrade`).",
        "--yes": "Auto-confirms all interactive prompts. Recommended for CI/CD.",
        "--dry-run": "Preview only - shows what would run without executing anything.",
        "--web": "Web build (always in release mode).",
        "--apk": "Android APK build.",
        "--aab": "Android App Bundle (AAB) build - for Play Store upload.",
        "--ipa": "IPA build for App Store (macOS only).",
        "-m debug": "Build in debug mode (default is release).",
        "--verbose": "Verbose flutter output - useful for debugging.",
        "--no-obfuscate": "Skip obfuscation on release builds.",
        "--sizes": "Shows build artifact sizes (APK, AAB, IPA, web).",
        "--doctor": "Runs `flutter doctor -v` - checks the environment.",
        "--devices": "Lists connected devices and Flutter/Dart versions.",
        "--emulators": "Lists available emulators.",
        "--deps": "Displays the full dependency tree (`pub deps`).",
        "--outdated": "Shows outdated packages (`flutter pub outdated`).",
        "--disk": "Disk usage summary: build, pub cache, .dart_tool.",
        "--android-licenses": "Accepts Android SDK licenses (`sdkmanager --licenses`).",
        "-p ios": "Generate iOS icons only.",
        "-p android": "Generate Android icons only.",
        "-p web": "Generate Web icons only.",
        "-n": "Only generate missing files - skips existing ones.",
        "--include-commented": "Counts commented-out imports as real imports (not recommended).",
        "clean": "Show Clean & Reinstall usage.",
        "info": "Show Info & Diagnostics usage.",
        "unused": "Show Unused Dart Files usage.",
        "translations": "Show Translation Checker usage.",
        "icons": "Show Icon Generator usage.",
        "build": "Show Build usage.",
        "run": "Show Run launcher usage.",
        "--env": "Shows installed tools: Java, Android SDK, Node.js, Firebase CLI, Git, etc.",
        "--windows": "Build Windows desktop app (.exe). Requires Windows.",
        "--macos": "Build macOS desktop app (.app). Requires macOS.",
        "--linux": "Build Linux desktop app (ELF binary). Requires Linux.",
        "--desktop": "Build for the current desktop platform (Windows + macOS + Linux - skips unsupported ones).",
        "-p windows": "Generate Windows icons (.ico) only.",
        "-p macos": "Generate macOS icons (appiconset) only.",
        "-p linux": "Generate Linux icons (PNG) only.",
        "--coverage": "Collect code coverage and generate lcov.info.",
        "--html": "Generate HTML coverage report from lcov.info (requires genhtml).",
        "--reporter expanded": "Detailed test output with individual test names.",
        "--reporter json": "JSON format test output for CI/CD parsing.",
        "--analyze": "Run flutter analyze - static analysis on lib/.",
        "--fatal-infos": "Treat info-level analysis issues as errors.",
        "--no-fatal-warnings": "Don't treat warnings as fatal in analysis.",
        "--fix": "Apply dart fix suggestions (modifies files!).",
        "--fix-preview": "Preview dart fix changes without applying.",
        "--format": "Format lib/ with dart format (modifies files!).",
        "--format-check": "Check formatting without modifying any files.",
        "--metrics": "Show code metrics: file count, lines, comments, ratios.",
        "--config": "Shows Flutter config: enabled platforms, analytics, etc.",
        "--no-backup": "Skip remote backup before uploading. Faster but no rollback option!",
        "--list-targets": "List all configured deploy targets and their status, then exit.",
        "deploy": "Show Deploy usage.",
        "--format zip": "Universal ZIP archive. Works everywhere, decent compression.",
        "--format tar.gz": "TAR + GZip. Fast compression, good ratio. Standard on Unix.",
        "--format tar.bz2": "TAR + BZip2. Slower than gzip, slightly better ratio.",
        "--format tar.xz": "TAR + XZ. Best compression ratio, but significantly slower.",
        "--format tar": "Plain TAR, no compression. Fastest, largest file.",
        "--format 7z": "7-Zip archive with encrypted headers. Best security + good compression.",
        "--format tar.zst": "TAR + Zstandard. Modern format: near-xz ratio at gz speed.",
        "--no-default-excludes": "Include build/, .dart_tool/ etc. in the archive. Much larger and slower.",
        "--keep 3": "After backup, keep only the 3 most recent backup files.",
        "--keep 5": "After backup, keep only the 5 most recent backups.",
        "--keep 10": "After backup, keep only the 10 most recent backups.",
        "--keep 20": "After backup, keep only the 20 most recent backups.",
        "sonar": "Run SonarScanner from the project root using the configured scanner.",
        "backup": "Show Backup usage.",
        "test": "Show Test usage.",
        "analyze": "Show Analyze & Format usage.",
        "--derived-data": "Deletes Xcode DerivedData/Runner-* folders (macOS only).",
        "--pub-outdated": "Runs `flutter pub outdated` - report only, no changes.",
        "--pub-deps": "Runs `flutter pub deps` - shows full dependency tree.",
        "--upgrade-dry-run": "Preview what pub upgrade would change without applying it.",
        "--pub-offline": "Resolves packages from local cache only (--offline).",
        "--pub-enforce-lockfile": "Requires pubspec.lock to match exactly. For CI/prod.",
        "--no-precompile": "Skip precompiling packages during pub get.",
        "--no-example": "Skip fetching example/ dependencies.",
        "--pod-install": "Runs `pod install` in ios/ (and macos/ if present).",
        "--pod-repo-update": "Runs `pod install --repo-update` - updates spec repos first.",
        "--pod-clean-install": "Runs `pod install --clean-install` - ignores lockfile.",
        "--pod-verbose": "Runs `pod install --verbose` - detailed CocoaPods output.",
        "--pod-update": "Runs `pod update` - upgrades all pods to latest versions.",
        "--pod-update-no-repo": "Runs `pod update --no-repo-update` - skips spec repo refresh.",
        "--pod-deintegrate": "Runs `pod deintegrate` - removes CocoaPods from project.",
        "--pod-cache-clean": "Runs `pod cache clean --all` - clears local pod cache.",
        "--pod-repo-list": "Runs `pod repo list` - shows configured spec repositories.",
        "--pod-env": "Runs `pod env` - shows CocoaPods environment info.",
        "--open-xcode": "Opens ios/Runner.xcworkspace in Xcode after operations.",
        "--mac-setup": "Configures Flutter PATH, Xcode, Rosetta, CocoaPods and opens workspaces.",
        "--format 7z": "7-Zip archive with encrypted headers. Best security + good compression.",
        "--format tar.zst": "TAR + Zstandard. Modern format: near-xz ratio at gz speed.",
        "--firebase": "Checks Firebase CLI login status and lists available projects.",
        "--build": "Runs `dart run build_runner build` once. Generates all annotated code (freezed, json_serializable, injectable, drift, etc.).",
        "--watch": "Runs `dart run build_runner watch` - watches for file changes and re-generates continuously. Use the Stop button to exit.",
        "--delete-conflicting": "Passes --delete-conflicting-outputs. Automatically resolves conflicts instead of asking interactively. Recommended for most cases.",
        "--flutter-gen": "Runs flutter_gen to generate type-safe asset accessors. Use Assets.images.logo.image() instead of raw strings.",
        "codegen": "Show Code Generation usage.",
    };
    footerEl.textContent = `\u00a9 ${new Date().getFullYear()} NHZ`;
    const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    function formatTime(date) {
        const h = date.getHours();
        const ampm = h >= 12 ? "PM" : "AM";
        const h12 = h % 12 || 12;
        return `${h12}:${pad(date.getMinutes())}:${pad(date.getSeconds())} ${ampm}`;
    }
    const pad = n => String(n).padStart(2, "0");
    // Stopwatch
    function startRunTimer() {
        runStart = Date.now();
        runTimer = setInterval(() => {
            const elapsed = ((Date.now() - runStart) / 1000).toFixed(1);
            sbDuration.textContent = `${elapsed}s`;
        }, 100);
    }
    function stopRunTimer() {
        if (runTimer) { clearInterval(runTimer); runTimer = null; }
    }
    // Sidebar badge
    function updateCmdBadge(cmdName) {
        if (!cmdName) { return; }
        const btn = navEl.querySelector(`.cmd-btn[data-cmd="${cmdName}"]`);
        if (!btn) { return; }
        const badge = btn.querySelector(".cmd-badge");
        if (!badge) { return; }
        const count = cmdLineCounts[cmdName] ?? 0;
        badge.textContent = count > 999 ? "999+" : count;
        badge.hidden = count === 0;
        const suffix = count === 1 ? "line" : "lines";
        badge.title = count > 0 ? `${count} ${suffix} from last run` : "";
    }
    function resetCmdBadge(cmdName) {
        if (!cmdName) { return; }
        cmdLineCounts[cmdName] = 0;
        updateCmdBadge(cmdName);
    }
    // Shortcuts panel (welcome screen)
    function syncShortcutsPanel() {
        const panel = $("shortcuts-panel");
        const toggle = $("shortcuts-toggle");
        if (!panel || !toggle) { return; }
        panel.classList.toggle("collapsed", shortcutsCollapsed);
        toggle.setAttribute("aria-expanded", String(!shortcutsCollapsed));
    }
    configEl.addEventListener("click", (e) => {
        if (!e.target.closest("#shortcuts-toggle")) { return; }
        shortcutsCollapsed = !shortcutsCollapsed;
        localStorage.setItem("toolkit-shortcuts-collapsed", shortcutsCollapsed ? "1" : "0");
        syncShortcutsPanel();
    });
    // Sound
    function syncSoundBtn() {
        $("icon-sound-on").hidden = !soundEnabled;
        $("icon-sound-off").hidden = soundEnabled;
        soundBtn.classList.toggle("muted", !soundEnabled);
        soundBtn.title = soundEnabled ? "Sound ON (click to mute)" : "Sound OFF (click to unmute)";
        soundBtn.setAttribute("aria-label", soundBtn.title);
    }
    soundBtn.addEventListener("click", () => {
        soundEnabled = !soundEnabled;
        localStorage.setItem("toolkit-sound", soundEnabled ? "1" : "0");
        syncSoundBtn();
        if (soundEnabled) { playSound("success"); } // preview
    });
    // Auto-clear
    function syncAutoClearBtn() {
        autoClearBtn.classList.toggle("active", autoClearEnabled);
        autoClearBtn.title = autoClearEnabled
            ? "Auto-clear ON - output cleared before each run (click to disable)"
            : "Auto-clear OFF - click to enable";
    }
    autoClearBtn.addEventListener("click", () => {
        autoClearEnabled = !autoClearEnabled;
        localStorage.setItem("toolkit-autoclear", autoClearEnabled ? "1" : "0");
        syncAutoClearBtn();
    });
    function getAudioCtx() {
        if (!audioCtx) { audioCtx = new (globalThis.AudioContext || globalThis.webkitAudioContext)(); }
        if (audioCtx.state === "suspended") { audioCtx.resume(); }
        return audioCtx;
    }
    function playSound(type) {
        if (!soundEnabled) { return; }
        try {
            const ctx = getAudioCtx();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.type = "sine";
            gain.gain.setValueAtTime(0.25, ctx.currentTime);
            if (type === "success") {
                osc.frequency.setValueAtTime(523, ctx.currentTime);
                osc.frequency.setValueAtTime(659, ctx.currentTime + 0.12);
                osc.frequency.setValueAtTime(784, ctx.currentTime + 0.24);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.5);
            } else if (type === "error") {
                osc.frequency.setValueAtTime(392, ctx.currentTime);
                osc.frequency.setValueAtTime(311, ctx.currentTime + 0.2);
                osc.frequency.setValueAtTime(261, ctx.currentTime + 0.4);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.6);
            } else if (type === "prompt") {
                osc.frequency.setValueAtTime(440, ctx.currentTime);
                osc.frequency.setValueAtTime(554, ctx.currentTime + 0.15);
                osc.frequency.setValueAtTime(440, ctx.currentTime + 0.3);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.5);
            } else if (type === "notify") {
                osc.frequency.setValueAtTime(587, ctx.currentTime);
                osc.frequency.setValueAtTime(698, ctx.currentTime + 0.1);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.3);
            }
        } catch {
            // Audio not supported
        }
    }
    document.addEventListener("click", () => { getAudioCtx(); }, { once: true });
    // Filter
    function applyFilter(filter) {
        activeFilter = filter;
        for (const btn of filterBar.querySelectorAll(".filter-btn")) {
            btn.classList.toggle("active", btn.dataset.filter === filter);
        }
        for (const div of outEl.querySelectorAll("div")) {
            filter === "all" ? div.classList.remove("filter-hidden") : div.classList.toggle("filter-hidden", !div.classList.contains(filter));
        }
        updateSbLines();
    }
    filterBar.addEventListener("click", (e) => {
        const btn = e.target.closest(".filter-btn");
        if (btn) { applyFilter(btn.dataset.filter); }
    });
    function toggleFilter() {
        filterVisible = !filterVisible;
        filterBar.classList.toggle("hidden", !filterVisible);
        filterBar.classList.toggle("visible", filterVisible);
        filterToggleBtn.classList.toggle("active", filterVisible);
        if (!filterVisible) { applyFilter("all"); }
    }
    filterToggleBtn.addEventListener("click", toggleFilter);
    $("filter-close").addEventListener("click", () => {
        if (filterVisible) { toggleFilter(); }
    });
    // StatusBar
    function clearStatusBar() {
        sbLines.textContent = "";
        sbCmd.textContent = "";
        sbResult.textContent = "";
        sbResult.className = "sb-item";
        sbDuration.textContent = "";
        sbProgress.textContent = "";
        sbProgress.className = "sb-item";
        sbTime.textContent = "";
        delete sbTime.dataset.lastrun;
        sbTime.title = "";
    }
    function updateSbLines() {
        const all = outEl.querySelectorAll("div").length;
        const visible = outEl.querySelectorAll("div:not(.filter-hidden)").length;
        if (!all) { sbLines.textContent = ""; return; }
        if (activeFilter === "all" || all === visible) {
            const suffix = all === 1 ? "line" : "lines";
            sbLines.textContent = `${all} ${suffix}`;
        } else {
            sbLines.textContent = `${visible}/${all} lines`;
        }
    }
    function trimOutput() {
        const divs = outEl.querySelectorAll("div");
        if (divs.length <= MAX_OUTPUT_LINES) { return; }
        const excess = divs.length - MAX_OUTPUT_LINES;
        for (let i = 0; i < excess; i++) { divs[i].remove(); }
    }
    function updateSbRunInfo(exitCode, duration, cmdName) {
        const ok = exitCode === 0;
        const now = new Date();
        if (cmdName && config?.commands?.[cmdName]) { sbCmd.textContent = config.commands[cmdName].title; }
        sbResult.textContent = ok ? `✓ exit 0` : `✗ exit ${exitCode}`;
        sbResult.className = `sb-item ${ok ? "ok" : "fail"}`;
        sbDuration.textContent = duration == null ? "" : `${duration}s`;
        const timeStr = formatTime(now);
        sbTime.textContent = timeStr;
        sbTime.dataset.lastrun = "1";
        sbTime.title = `Last run finished: ${timeStr}`;
        if (cmdName) localStorage.setItem(`toolkit-lastrun-${cmdName}`, JSON.stringify({ exitCode, duration, time: now.toISOString() }));
        updateRunBtnTooltip(cmdName);
    }
    function updateRunBtnTooltip(cmdName) {
        if (!cmdName) { return; }
        const saved = localStorage.getItem(`toolkit-lastrun-${cmdName}`);
        if (!saved) { runBtn.title = kbd("Run command (Ctrl+Enter)"); return; }
        const { exitCode, duration, time } = JSON.parse(saved);
        const d = new Date(time);
        const t = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
        runBtn.title = `${kbd("Run command (Ctrl+Enter)")}  ·  Last: ${exitCode === 0 ? "✓" : "✗"} ${duration}s @ ${t}`;
    }
    // Config collapse
    let configCollapsed = localStorage.getItem("toolkit-config-collapsed") === "1";
    let outputCollapsed = localStorage.getItem("toolkit-output-collapsed") === "1";
    function syncConfigCollapse() {
        configEl.classList.toggle("collapsed", configCollapsed);
        collapseConfigBtn.classList.toggle("collapsed", configCollapsed);
        collapseConfigBtn.title = configCollapsed
            ? kbd("Expand config panel (Ctrl+Shift+B)")
            : kbd("Collapse config panel (Ctrl+Shift+B)");
        collapseConfigBtn.setAttribute("aria-expanded", String(!configCollapsed));
    }
    collapseConfigBtn.addEventListener("click", () => {
        if (outputCollapsed) {
            outputCollapsed = false;
            localStorage.setItem("toolkit-output-collapsed", "0");
            syncOutputCollapse();
        }
        configCollapsed = !configCollapsed;
        localStorage.setItem("toolkit-config-collapsed", configCollapsed ? "1" : "0");
        syncConfigCollapse();
    });
    function syncOutputCollapse() {
        const outWrap = document.querySelector(".output-wrap");
        outWrap.classList.toggle("collapsed", outputCollapsed);
        configEl.classList.toggle("expanded", outputCollapsed);
        collapseOutBtn.classList.toggle("collapsed", outputCollapsed);
        collapseOutBtn.title = outputCollapsed
            ? kbd("Show output panel (Ctrl+Alt+B)")
            : kbd("Expand config / collapse output (Ctrl+Alt+B)");
        collapseOutBtn.setAttribute("aria-expanded", String(!outputCollapsed));
    }
    collapseOutBtn.addEventListener("click", () => {
        if (!activeCmd) { return; }
        if (configCollapsed) {
            configCollapsed = false;
            localStorage.setItem("toolkit-config-collapsed", "0");
            syncConfigCollapse();
        }
        outputCollapsed = !outputCollapsed;
        localStorage.setItem("toolkit-output-collapsed", outputCollapsed ? "1" : "0");
        syncOutputCollapse();
    });
    // Sidebar collapse
    let sidebarCollapsed = localStorage.getItem("toolkit-sidebar-collapsed") === "1";
    function syncSidebarCollapse() {
        const isMobile = globalThis.matchMedia("(max-width:768px)").matches;
        sidebarEl.classList.toggle("collapsed", !isMobile && sidebarCollapsed);
        sidebarCollapseBtn.title = sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar";
        sidebarCollapseBtn.hidden = isMobile;
        for (const b of navEl.querySelectorAll(".cmd-btn")) {
            const cmd = config?.commands?.[b.dataset.cmd];
            b.title = sidebarCollapsed && cmd ? cmd.title : cmd?.description ?? "";
        }
    }
    sidebarCollapseBtn.addEventListener("click", () => {
        if (globalThis.matchMedia("(max-width:768px)").matches) { return; }
        sidebarCollapsed = !sidebarCollapsed;
        localStorage.setItem("toolkit-sidebar-collapsed", sidebarCollapsed ? "1" : "0");
        syncSidebarCollapse();
    });
    sidebarEl.addEventListener("transitionend", hideTip);
    // Theme
    function initTheme() {
        const saved = localStorage.getItem("toolkit-theme");
        if (saved === "dark" || (!saved && matchMedia("(prefers-color-scheme:dark)").matches)) {
            document.body.classList.add("dark");
        }
        syncThemeBtn();
    }
    function syncThemeBtn() {
        const isDark = document.body.classList.contains("dark");
        $("icon-sun").hidden = isDark;
        $("icon-moon").hidden = !isDark;
        themeBtn.title = isDark ? "Switch to light theme" : "Switch to dark theme";
        themeBtn.setAttribute("aria-label", themeBtn.title);
    }
    themeBtn.addEventListener("click", () => {
        document.body.classList.toggle("dark");
        localStorage.setItem("toolkit-theme", document.body.classList.contains("dark") ? "dark" : "light");
        syncThemeBtn();
    });
    // Logo -> Welcom
    logoBtn.addEventListener("click", () => {
        if (running) { return; }
        if (outputCollapsed) {
            outputCollapsed = false;
            localStorage.setItem("toolkit-output-collapsed", "0");
            syncOutputCollapse();
        }
        activeCmd = null;
        document.body.classList.remove("fullscreen-mode", "hide-run-controls");
        for (const b of navEl.querySelectorAll(".cmd-btn")) { b.classList.remove("active"); }
        configEl.innerHTML = welcomeHTML;
        syncShortcutsPanel();
        ctrlEl.dataset.hidden = "";
        outEl.innerHTML = "";
        runBtn.title = kbd("Run command (Ctrl+Enter)");
        document.title = BASE_TITLE;
        hideSearch();
        clearStatusBar();
        for (const key of Object.keys(cmdLineCounts)) { resetCmdBadge(key); }
        lastClearedOutput = null;
        lastClearedBadges = null;
        lastClearedStatusBar = null;
        if (configCollapsed) {
            configCollapsed = false;
            localStorage.setItem("toolkit-config-collapsed", "0");
            syncConfigCollapse();
        }
        if (filterVisible) {
            filterVisible = false;
            filterBar.classList.add("hidden");
            filterBar.classList.remove("visible");
            filterToggleBtn.classList.remove("active");
        }
        document.body.classList.add("welcome-mode");
        syncButtons();
    });
    function checkBusy() {
        fetch("/api/status")
            .then(r => r.json())
            .then(data => {
                if (data.busy) { appendLine(`\u26a0 Another client is running: ${data.command}`, "line-warn"); }
            })
            .catch(() => { });
    }
    // WebSocket
    function connectWs() {
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        ws = new WebSocket(`${proto}//${location.host}/ws`);
        ws.onopen = () => {
            wsDot.className = "dot on";
            meta.textContent = config ? `${config.platform} \u2022 ${config.project_root}` : "Connected";
            loadConfig();
            checkBusy();
            refreshProjectSwitcher();
        };
        ws.onclose = () => {
            wsDot.className = "dot off";
            meta.textContent = "Disconnected \u2014 retrying...";
            if (running) {
                appendLine("");
                appendLine("\u26a0 Connection lost \u2014 process state unknown", "line-warn");
            }
            stopRunTimer();
            setRunningBtn(runningCmd, false);
            runningCmd = null;
            running = false;
            syncButtons();
            setTimeout(connectWs, 2500);
        };
        ws.onmessage = (e) => handleMsg(JSON.parse(e.data));
    }
    function handleMsg(msg) {
        switch (msg.type) {
            case "start":
                sbProgress.textContent = "";
                sbProgress.className = "sb-item";
                startRunTimer();
                if (autoClearEnabled) { resetCmdBadge(runningCmd); }
                document.title = `\u25b6 Running... \u2013 ${BASE_TITLE}`;
                appendLine(msg.data, "line-cmd");
                appendLine("\u2500".repeat(56), "line-head");
                break;
            case "output":
                appendLine(msg.data, classifyLine(msg.data));
                break;
            case "exit": {
                const dur = msg.duration ? ` in ${msg.duration}s` : "";
                const ok = msg.code === 0;
                stopRunTimer();
                playSound(ok ? "success" : "error");
                appendLine("");
                appendLine(ok ? `Done (exit code 0${dur})` : `Failed (exit code ${msg.code}${dur})`, ok ? "status ok" : "status fail");
                document.title = `${ok ? "\u2714" : "\u2718"} ${ok ? "Done" : "Failed"} \u2013 ${BASE_TITLE}`;
                updateSbRunInfo(msg.code, msg.duration, runningCmd);
                setRunningBtn(runningCmd, false);
                runningCmd = null;
                running = false;
                syncButtons();
                break;
            }
            case "stopped":
                appendLine(`Stopped. ${msg.data}`, "status fail");
                stopRunTimer();
                document.title = BASE_TITLE;
                setRunningBtn(runningCmd, false);
                runningCmd = null;
                running = false;
                syncButtons();
                break;
            case "notify":
                playSound("notify");
                showNotification(msg.title, msg.body);
                break;
            case "error":
                appendLine(`Error: ${msg.data}`, "line-err");
                stopRunTimer();
                setRunningBtn(runningCmd, false);
                runningCmd = null;
                running = false;
                syncButtons();
                break;
            case "info":
                appendLine(msg.data, "line-info");
                break;
            case "prompt":
                playSound("prompt")
                showPromptModal(msg.data);
                break;
        }
    }
    function showPromptModal(question) {
        requestNotifyPermission();
        showNotification("Input required", question);
        askConfirm({
            title: "Input required",
            message: question,
            okLabel: "Yes (Enter)",
            cancelLabel: "No (ESC)",
            onOk: () => ws.send(JSON.stringify({ action: "answer", value: "y" })),
            onCancel: () => ws.send(JSON.stringify({ action: "stop" })),
        });
    }
    // Notifications
    function requestNotifyPermission() {
        if ("Notification" in globalThis && Notification.permission === "default") { Notification.requestPermission(); }
    }
    function showNotification(title, body) {
        if (document.hasFocus()) { return; }
        if ("Notification" in globalThis && Notification.permission === "granted") { new Notification(title, { body, icon: "/favicon.ico" }); }
    }
    // Output
    function classifyLine(t) {
        if (t.includes("✔") || t.includes("[OK]")) { return "line-ok"; }
        if (t.includes("⚠") || t.includes("[WARN]")) { return "line-warn"; }
        if (t.includes("✘") || t.includes("FAIL") || t.includes("[ERROR]")) { return "line-err"; }
        if (t.includes("===") || t.includes("---")) { return "line-head"; }
        if (t.trimStart().startsWith("$")) { return "line-cmd"; }
        return "line-info";
    }
    function appendLine(text, cls) {
        const div = document.createElement("div");
        if (cls) { div.className = cls; }
        div.textContent = text;
        outEl.appendChild(div);
        if (autoScroll) { outEl.scrollTop = outEl.scrollHeight; }
        if (searchActive && searchQuery) { rehighlightLine(div); }
        const pm = text.match(/\[(\d+)\/(\d+)\]/);
        if (pm) {
            sbProgress.textContent = `${pm[1]} / ${pm[2]}`;
            sbProgress.className = "sb-item progress";
        }
        if (runningCmd) {
            cmdLineCounts[runningCmd] = (cmdLineCounts[runningCmd] ?? 0) + 1;
            updateCmdBadge(runningCmd);
        }
        updateSbLines();
        if (activeFilter !== "all" && !div.classList.contains(activeFilter)) {
            div.classList.add("filter-hidden");
        }
        trimOutput();
    }
    // Auto-scroll
    function syncScrollBtn() {
        scrollBotBtn.classList.toggle("active", autoScroll);
        scrollBotBtn.title = autoScroll
            ? "Auto-scroll ON (click to pin)"
            : "Auto-scroll OFF (click to follow)";
    }
    outEl.addEventListener("scroll", () => {
        const atBottom = outEl.scrollHeight - outEl.scrollTop - outEl.clientHeight < 30;
        if (!atBottom && autoScroll) { autoScroll = false; syncScrollBtn(); }
        else if (atBottom && !autoScroll) { autoScroll = true; syncScrollBtn(); }
    });
    // Config / Sidebar
    function loadConfig() {
        fetch("/api/config")
            .then(r => { if (!r.ok) { throw new Error(r.status); } return r.json(); })
            .then(data => {
                config = data;
                meta.textContent = `${config.platform} • ${config.project_root}`;
                renderSidebar();
            })
            .catch(err => {
                meta.textContent = "Config load failed";
                console.error("Config fetch error:", err);
            });
    }
    function renderSidebar() {
        navEl.innerHTML = "";
        const tpl = $("tpl-cmd-btn");
        for (const [key, cmd] of Object.entries(config.commands)) {
            const frag = tpl.content.cloneNode(true);
            const btn = frag.querySelector(".cmd-btn");
            btn.dataset.cmd = key;
            if (cmd.disabled) {
                btn.disabled = true;
                btn.classList.add("cmd-disabled");
                btn.title = cmd.disabled_reason || "Coming soon";
            } else {
                btn.title = cmd.description;
                btn.addEventListener("click", () => selectCmd(key));
            }
            btn.querySelector(".cmd-icon").innerHTML =
                cmd.icon ? `<svg width="16" height="16"><use href="#icon-${cmd.icon}"/></svg>` : "";
            btn.querySelector(".cmd-title").textContent = cmd.title;
            navEl.appendChild(btn);
        }
        syncSidebarCollapse();
    }
    function selectCmd(name) {
        document.body.classList.remove("welcome-mode");
        document.body.classList.toggle("fullscreen-mode", !!config.commands[name]?.fullscreen);
        document.body.classList.toggle("hide-run-controls", !!config.commands[name]?.hide_run_controls);
        for (const key of Object.keys(localStorage)) {
            if (key.startsWith("toolkit-group-collapsed-")) { localStorage.removeItem(key); }
        }
        activeCmd = name;
        if (configCollapsed) {
            configCollapsed = false;
            localStorage.setItem("toolkit-config-collapsed", "0");
            syncConfigCollapse();
        }
        for (const b of navEl.querySelectorAll(".cmd-btn")) {
            b.classList.toggle("active", b.dataset.cmd === name);
        }
        renderConfigPanel(config.commands[name], name);
        configEl.scrollTop = 0;
        if (filterVisible) {
            filterVisible = false;
            filterBar.classList.add("hidden");
            filterBar.classList.remove("visible");
            filterToggleBtn.classList.remove("active");
        }
        applyFilter("all");
        delete ctrlEl.dataset.hidden;
        syncPreview();
        syncButtons();
        updateRunBtnTooltip(name);
    }
    // Render config panel
    function renderOptRowDOM(opt, name, gi, oi) {
        const frag = $("tpl-opt-row").content.cloneNode(true);
        const row = frag.querySelector(".opt-row");
        const id = `opt_${name}_g${gi}_${oi}`;
        const cb = frag.querySelector("input");
        cb.id = id;
        cb.dataset.flag = opt.flag;
        if (opt.default) { cb.checked = true; }
        if (opt.disabled) {
            cb.disabled = true;
            row.classList.add("opt-disabled");
        }
        const labelText = frag.querySelector(".label-text");
        labelText.textContent = opt.label;
        const tip = opt.tip || FLAG_TIPS[opt.flag];
        if (tip) {
            const tipFrag = $("tpl-flag-tip-btn").content.cloneNode(true);
            const tipBtn = tipFrag.querySelector(".flag-tip-btn");
            tipBtn.dataset.tip = tip;
            tipBtn.setAttribute("aria-label", `Info: ${tip}`);
            row.appendChild(tipBtn);
        }
        return row;
    }
    function renderGroupDOM(grp, name, gi) {
        const frag = $("tpl-group").content.cloneNode(true);
        const groupEl = frag.querySelector(".group");
        const header = frag.querySelector(".group-header");
        const labelEl = header.querySelector(".group-label");
        labelEl.textContent = grp.label;
        if (grp.type === "dynamic_folders" || (grp.options && grp.options.length > 1)) { groupEl.classList.add("collapsible"); }
        const stateKey = `toolkit-group-collapsed-${name}-${grp.label}`;
        if (localStorage.getItem(stateKey) === "1") { groupEl.classList.add("collapsed"); }
        labelEl.addEventListener("click", () => {
            const nowCollapsed = groupEl.classList.toggle("collapsed");
            localStorage.setItem(stateKey, nowCollapsed ? "1" : "0");
        });
        if (grp.type === "checkboxes") {
            const actFrag = $("tpl-group-actions").content.cloneNode(true);
            const checkBtn = actFrag.querySelector(".check-all-btn");
            const uncheckBtn = actFrag.querySelector(".uncheck-all-btn");
            checkBtn.dataset.gi = gi;
            checkBtn.dataset.cmd = name;
            uncheckBtn.dataset.gi = gi;
            uncheckBtn.dataset.cmd = name;
            actFrag.querySelectorAll("button").forEach(b => {
                b.addEventListener("click", e => e.stopPropagation());
            });
            header.appendChild(actFrag);
        }
        if (grp.hint) {
            const hint = document.createElement("div");
            hint.className = "group-hint";
            hint.textContent = grp.hint;
            groupEl.appendChild(hint);
        }
        if (grp.type === "checkboxes") {
            grp.options.forEach((opt, oi) => groupEl.appendChild(renderOptRowDOM(opt, name, gi, oi)));
        } else if (grp.type === "select") {
            const sel = document.createElement("select");
            grp.options.forEach(o => {
                const opt = document.createElement("option");
                opt.value = o.flag;
                opt.textContent = o.label;
                sel.appendChild(opt);
            });
            groupEl.appendChild(sel);
        } else if (grp.type === "dynamic_folders") {
            renderDynamicFolders(grp, groupEl, name, gi);
        }
        return groupEl;
    }
    function syncPresetActive(cmd) {
        if (!cmd.presets?.length) { return; }
        const currentFlags = new Set();
        for (const cb of configEl.querySelectorAll('input[type="checkbox"]:checked:not(:disabled)')) {
            if (cb.dataset.flag.startsWith("--exclude ")) { continue; }
            currentFlags.add(cb.dataset.flag);
        }
        for (const sel of configEl.querySelectorAll("select:not(:disabled)")) {
            if (sel.value) { currentFlags.add(sel.value); }
        }
        for (const btn of configEl.querySelectorAll(".preset-btn")) {
            const preset = cmd.presets[btn.dataset.pi];
            const presetFlags = new Set(preset.flags);
            const match = presetFlags.size === currentFlags.size &&
                [...presetFlags].every(f => currentFlags.has(f));
            btn.classList.toggle("active", match);
        }
    }
    function renderNotesPanel(cmd) {
        activeConfig = cmd;
        configEl.innerHTML = "";
        renderHeader(cmd);
        const wrap = document.createElement("div");
        wrap.className = "notes-wrap";
        const textarea = document.createElement("textarea");
        textarea.className = "notes-textarea";
        textarea.placeholder = "Write your notes here...";
        textarea.spellcheck = false;
        const actions = document.createElement("div");
        actions.className = "notes-actions";
        const statusEl = document.createElement("span");
        statusEl.className = "notes-status";
        actions.appendChild(statusEl);
        const saveBtn = document.createElement("button");
        saveBtn.type = "button";
        saveBtn.className = "btn btn-notes-save";
        saveBtn.title = "Save (Ctrl+S)";
        saveBtn.innerHTML = `<svg width="13" height="13"><use href="#icon-save"/></svg>`;
        actions.appendChild(saveBtn);
        wrap.appendChild(actions);
        wrap.appendChild(textarea);
        configEl.appendChild(wrap);
        let dirty = false;
        fetch("/api/notes")
            .then(r => r.json())
            .then(d => {
                textarea.value = d.content ?? "";
                statusEl.textContent = "Loaded";
                statusEl.className = "notes-status ok";
            })
            .catch(() => {
                statusEl.textContent = "⚠ Failed to load";
                statusEl.className = "notes-status fail";
            });
        function doSave() {
            if (!dirty) { return; }
            dirty = false;
            statusEl.textContent = "Saving...";
            statusEl.className = "notes-status";
            fetch("/api/notes", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ content: textarea.value }),
            })
                .then(r => r.json())
                .then(d => {
                    statusEl.textContent = d.ok ? "✔ Saved" : "⚠ Error";
                    statusEl.className = d.ok ? "notes-status ok" : "notes-status fail";
                })
                .catch(() => {
                    statusEl.textContent = "⚠ Save failed";
                    statusEl.className = "notes-status fail";
                    dirty = true;
                });
        }
        saveBtn.addEventListener("click", () => { dirty = true; doSave(); });
        textarea.addEventListener("keydown", (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); dirty = true; doSave(); }
        });
        textarea.addEventListener("input", () => {
            dirty = true;
            statusEl.textContent = "Unsaved changes";
            statusEl.className = "notes-status warn";
            textarea.style.height = "auto";
            textarea.style.height = textarea.scrollHeight + "px";
        });
        textarea.addEventListener("blur", doSave);
    }
    function renderStaticPanel(cmd) {
        activeConfig = cmd;
        configEl.innerHTML = "";
        renderHeader(cmd);
        const groups = groupCommands(cmd.run_commands);
        renderGroups(groups);
    }
    function renderHeader(cmd) {
        const h2 = document.createElement("h2");
        h2.textContent = cmd.title;
        configEl.appendChild(h2);
        const desc = document.createElement("p");
        desc.className = "desc";
        desc.textContent = cmd.description;
        configEl.appendChild(desc);
    }
    function groupCommands(commands = []) {
        const groups = {};
        for (const item of commands) {
            if (!groups[item.mode]) { groups[item.mode] = []; }
            groups[item.mode].push(item);
        }
        return groups;
    }
    function renderGroups(groups) {
        for (const [mode, items] of Object.entries(groups)) {
            const allDisabled = items.every(i => i.disabled);
            const groupEl = document.createElement("div");
            groupEl.className = "group" + (allDisabled ? " group-run-disabled" : "");
            const header = document.createElement("div");
            header.className = "group-header";
            const label = document.createElement("div");
            label.className = "group-label";
            label.textContent = mode;
            header.appendChild(label);
            if (allDisabled) {
                const badge = document.createElement("span");
                badge.className = "run-soon-badge";
                badge.textContent = "coming soon";
                header.appendChild(badge);
            }
            groupEl.appendChild(header);
            for (const item of items) {
                groupEl.appendChild(createCommandRow(item));
            }
            configEl.appendChild(groupEl);
        }
    }
    function createCommandRow(item) {
        const row = document.createElement("div");
        row.className = "run-cmd-row" + (item.disabled ? " run-cmd-row-disabled" : "");
        const code = document.createElement("code");
        code.className = "run-cmd-code";
        code.textContent = cleanCommand(item.cmd);
        code.title = buildCmdTooltip(item.cmd);
        row.appendChild(code);
        if (!item.disabled) { row.appendChild(createCopyButton(code.textContent)); }
        return row;
    }
    function buildCmdTooltip(cmd) {
        const tips = [];
        if (cmd.includes("-d android")) { tips.push("-d android  = target device: any Android device/emulator"); }
        else if (cmd.includes("-d ios")) { tips.push("-d ios      = target device: any iOS device/simulator"); }
        else if (cmd.includes("-d chrome")) { tips.push("-d chrome   = target device: Chrome browser (web)"); }
        else if (cmd.includes("-d windows")) { tips.push("-d windows  = target device: Windows desktop"); }
        else if (cmd.includes("-d macos")) { tips.push("-d macos    = target device: macOS desktop"); }
        else if (cmd.includes("-d linux")) { tips.push("-d linux    = target device: Linux desktop"); }
        tips.push("-d          = short for --device-id");
        if (cmd.includes("--flavor")) { tips.push("--flavor    = build flavor (native Android/iOS/macOS only)"); }
        if (cmd.includes("--dart-define")) { tips.push("--dart-define = pass compile-time constant to Dart code"); }
        if (cmd.includes("--debug")) { tips.push("--debug     = debug mode (hot reload, assertions on)"); }
        if (cmd.includes("--release")) { tips.push("--release   = release mode (optimized, no debugging)"); }
        if (cmd.includes("--profile")) { tips.push("--profile   = profile mode (for performance analysis)"); }
        return tips.join("\n");
    }
    function cleanCommand(cmd) {
        return cmd.replaceAll(/\s+/g, " ").trim();
    }
    function createCopyButton(text) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn run-cmd-copy";
        btn.title = "Copy to clipboard";
        btn.textContent = "Copy";
        btn.addEventListener("click", () => handleCopyClick(btn, text));
        return btn;
    }
    function handleCopyClick(btn, text) {
        navigator.clipboard
            .writeText(text)
            .then(() => onCopySuccess(btn));
    }
    function onCopySuccess(btn) {
        btn.textContent = "Copied!";
        btn.classList.add("copied");
        setTimeout(() => resetCopyButton(btn), 1500);
    }
    function resetCopyButton(btn) {
        btn.textContent = "Copy";
        btn.classList.remove("copied");
    }
    function renderConfigPanel(cmd, name) {
        if (cmd.type === "notes") { renderNotesPanel(cmd); return; }
        if (cmd.static) { renderStaticPanel(cmd); return; }
        if (cmd.warning) {
            const banner = document.createElement("div");
            banner.className = "cmd-warning-banner";
            banner.textContent = cmd.warning;
            configEl.appendChild(banner);
        }
        activeConfig = cmd;
        configEl.innerHTML = "";
        const h2 = document.createElement("h2");
        h2.textContent = cmd.title;
        configEl.appendChild(h2);
        const desc = document.createElement("p");
        desc.className = "desc";
        desc.textContent = cmd.description;
        configEl.appendChild(desc);
        if (cmd.presets?.length) {
            const frag = $("tpl-presets-group").content.cloneNode(true);
            const presetsEl = frag.querySelector(".presets");
            const presetTpl = $("tpl-preset-btn");
            cmd.presets.forEach((p, i) => {
                const pFrag = presetTpl.content.cloneNode(true);
                const btn = pFrag.querySelector(".preset-btn");
                btn.dataset.pi = i;
                btn.textContent = p.label;
                btn.title = p.flags.join(" ") || "No flags = full reset";
                if (p.default) { btn.classList.add("active"); }
                if (p.disabled) { btn.disabled = true; }
                presetsEl.appendChild(btn);
            });
            configEl.appendChild(frag);
        }
        const cbGroupCount = cmd.groups.filter(g => g.type === "checkboxes").length;
        if (cbGroupCount > 1) {
            const frag = $("tpl-master-actions").content.cloneNode(true);
            frag.querySelector(".check-all-btn").dataset.cmd = name;
            frag.querySelector(".uncheck-all-btn").dataset.cmd = name;
            configEl.appendChild(frag);
        }
        cmd.groups.forEach((grp, gi) => configEl.appendChild(renderGroupDOM(grp, name, gi)));
        if (cmd.groups.length > 0) { configEl.appendChild($("tpl-reset-row").content.cloneNode(true)); }
        for (const el of configEl.querySelectorAll("input,select")) {
            el.addEventListener("change", () => { syncPreview(); syncPresetActive(cmd); syncBuildConstraints(); syncBackupConstraints(); });
        }
        for (const btn of configEl.querySelectorAll(".check-all-btn:not(.master-btn)")) {
            btn.addEventListener("click", () => setGroupChecked(btn.dataset.gi, btn.dataset.cmd, true));
        }
        for (const btn of configEl.querySelectorAll(".uncheck-all-btn:not(.master-btn)")) {
            btn.addEventListener("click", () => setGroupChecked(btn.dataset.gi, btn.dataset.cmd, false));
        }
        for (const btn of configEl.querySelectorAll(".master-btn.check-all-btn")) {
            btn.addEventListener("click", () => setAllChecked(true));
        }
        for (const btn of configEl.querySelectorAll(".master-btn.uncheck-all-btn")) {
            btn.addEventListener("click", () => setAllChecked(false));
        }
        for (const btn of configEl.querySelectorAll(".preset-btn")) {
            btn.addEventListener("click", () => {
                const preset = cmd.presets[btn.dataset.pi];
                const flagSet = new Set(preset.flags);
                for (const cb of configEl.querySelectorAll('input[type="checkbox"]')) {
                    if (cb.dataset.flag.startsWith("--exclude ")) {
                        const labelText = cb.closest(".opt-row")?.querySelector(".label-text")?.textContent ?? "";
                        cb.checked = labelText.includes("(default excluded)");
                    } else {
                        cb.checked = flagSet.has(cb.dataset.flag);
                    }
                }
                const selects = configEl.querySelectorAll("select");
                for (const sel of selects) {
                    const match = Array.from(sel.options).find(o => flagSet.has(o.value));
                    const newValue = match ? match.value : (sel.options[0]?.value ?? "");
                    sel.value = newValue;
                }
                for (const b of configEl.querySelectorAll(".preset-btn")) { b.classList.remove("active"); }
                btn.classList.add("active");
                syncPreview();
                syncBuildConstraints();
                syncBackupConstraints();
            });
        }
        function _resetCheckboxGroup(grp) {
            for (const opt of grp.options) {
                const cb = configEl.querySelector(`input[data-flag="${CSS.escape(opt.flag)}"]`);
                if (cb) { cb.checked = !!opt.default; }
            }
        }
        function _resetSelectGroup(grp) {
            const defaultOpt = grp.options.find(o => o.default);
            const targetValue = defaultOpt ? defaultOpt.flag : (grp.options[0]?.flag ?? "");
            for (const sel of configEl.querySelectorAll("select")) {
                if (!Array.from(sel.options).some(o => o.value === targetValue)) { continue; }
                if (sel.value === targetValue) { continue; }
                sel.value = targetValue;
                sel.dispatchEvent(new Event("change", { bubbles: true }));
            }
        }
        function _resetDynamicFoldersGroup() {
            for (const cb of configEl.querySelectorAll('input[data-flag^="--exclude "]')) {
                const labelText = cb.closest(".opt-row")?.querySelector(".label-text")?.textContent ?? "";
                cb.checked = labelText.includes("(default excluded)");
            }
        }
        function _resetGroup(grp) {
            if (grp.type === "checkboxes") { _resetCheckboxGroup(grp); }
            else if (grp.type === "select") { _resetSelectGroup(grp); }
            else if (grp.type === "dynamic_folders") { _resetDynamicFoldersGroup(); }
        }
        if (cmd.groups.length > 0) {
            $("config-reset-btn").addEventListener("click", () => {
                for (const grp of cmd.groups) { _resetGroup(grp); }
                syncPreview();
                syncPresetActive(activeConfig);
                syncBuildConstraints();
                syncBackupConstraints();
            });
        }
        attachTooltips();
        syncBuildConstraints();
    }
    function renderDynamicFolders(grp, groupEl, name, gi) {
        const loadingEl = document.createElement("div");
        loadingEl.className = "group-hint group-folders-loading";
        loadingEl.textContent = "Loading folders…";
        groupEl.appendChild(loadingEl);

        fetch("/api/folders")
            .then(r => { if (!r.ok) { throw new Error(r.status); } return r.json(); })
            .then(data => populateFolders(data, loadingEl, grp, groupEl, name, gi))
            .catch(() => {
                loadingEl.textContent = "⚠ Failed to load folders.";
                loadingEl.style.color = "var(--error)";
            });
    }
    function populateFolders(data, loadingEl, grp, groupEl, name, gi) {
        loadingEl.remove();
        const entries = (data.folders ?? []).map(normalizeFolder);
        if (!entries.length) {
            appendHint(groupEl, "No entries found in project root.");
            return;
        }
        appendGroupActions(groupEl, name, gi);
        entries.forEach((entry, oi) => {
            const suffix = entry.default_excluded ? "  (default excluded)" : "";
            const opt = {
                flag: `--exclude ${entry.name}`,
                label: `${entry.name}${suffix}`,
                disabled: false,
                default: entry.default_excluded,
            };
            const row = renderOptRowDOM(opt, name, gi, oi);
            const labelText = row.querySelector(".label-text");
            if (labelText) {
                const iconId = entry.is_dir ? "icon-folder" : "icon-file";
                const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
                svg.setAttribute("width", "14");
                svg.setAttribute("height", "14");
                svg.classList.add("entry-icon");
                const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
                use.setAttribute("href", `#${iconId}`);
                svg.appendChild(use);
                labelText.parentNode.insertBefore(svg, labelText);
            }
            groupEl.appendChild(row);
        });
        wireFolderEvents(groupEl);
        syncPreview();
    }
    function normalizeFolder(f) {
        if (typeof f === "string") { return { name: f, is_dir: true, default_excluded: false }; }
        return { is_dir: true, default_excluded: false, ...f };
    }
    function appendHint(groupEl, text) {
        const el = document.createElement("div");
        el.className = "group-hint";
        el.textContent = text;
        groupEl.appendChild(el);
    }
    function appendGroupActions(groupEl, name, gi) {
        const frag = $("tpl-group-actions").content.cloneNode(true);
        const checkBtn = frag.querySelector(".check-all-btn");
        const uncheckBtn = frag.querySelector(".uncheck-all-btn");
        checkBtn.dataset.gi = gi; checkBtn.dataset.cmd = name;
        uncheckBtn.dataset.gi = gi; uncheckBtn.dataset.cmd = name;
        frag.querySelectorAll("button").forEach(b => {
            b.addEventListener("click", e => e.stopPropagation());
        });
        groupEl.querySelector(".group-header").appendChild(frag);
    }
    function wireFolderEvents(groupEl) {
        groupEl.querySelectorAll("input").forEach(el =>
            el.addEventListener("change", () => { syncPreview(); syncBackupConstraints(); }));
        groupEl.querySelectorAll(".check-all-btn").forEach(btn =>
            btn.addEventListener("click", () =>
                setGroupChecked(btn.dataset.gi, btn.dataset.cmd, true)));
        groupEl.querySelectorAll(".uncheck-all-btn").forEach(btn =>
            btn.addEventListener("click", () =>
                setGroupChecked(btn.dataset.gi, btn.dataset.cmd, false)));
    }
    function syncBuildConstraints() {
        if (activeCmd !== "build") { return; }
        const flag = f => configEl.querySelector(`input[data-flag="${CSS.escape(f)}"]`);
        const hasWeb = flag("--web")?.checked ?? false;
        const hasApk = flag("--apk")?.checked ?? false;
        const hasAab = flag("--aab")?.checked ?? false;
        const hasIos = flag("--ios")?.checked ?? false;
        const hasIpa = flag("--ipa")?.checked ?? false;
        const anyChecked = hasWeb || hasApk || hasAab || hasIos || hasIpa;
        const effectiveObfuscatable = !anyChecked || hasApk || hasAab || hasIpa;
        const effectiveModeRelevant = !anyChecked || hasApk || hasAab || hasIos;
        _setDisabled(flag("--no-obfuscate"),
            !effectiveObfuscatable,
            "Relevant only for APK / AAB / IPA builds");
        const modeSelect = configEl.querySelector("select");
        if (!modeSelect) { return; }
        const releaseOnly = anyChecked && !effectiveModeRelevant;
        for (const opt of modeSelect.options) {
            if (opt.value.includes("debug")) { opt.disabled = releaseOnly; }
        }
        if (releaseOnly && modeSelect.value.includes("debug")) { modeSelect.selectedIndex = 0; }
        modeSelect.disabled = releaseOnly;
        modeSelect.title = releaseOnly ? "Web and IPA are always built in release mode" : "";
        modeSelect.closest(".group")?.classList.toggle("group-disabled", releaseOnly);
    }
    function syncBackupConstraints() {
        if (activeCmd !== "backup") { return; }
        const noDefaultCb = configEl.querySelector('input[data-flag="--no-default-excludes"]');
        if (!noDefaultCb) { return; }
        const noDefault = noDefaultCb.checked;
        for (const cb of configEl.querySelectorAll('input[data-flag^="--exclude "]')) {
            if (noDefault) {
                _setDisabled(cb, true, "--no-default-excludes aktív — egyedi kizárások figyelmen kívül maradnak");
            } else {
                const wasDisabled = cb.disabled;
                _setDisabled(cb, false, "");
                if (wasDisabled) {
                    const labelText = cb.closest(".opt-row")?.querySelector(".label-text")?.textContent ?? "";
                    cb.checked = labelText.includes("(default excluded)");
                }
            }
        }
    }
    function _setDisabled(cb, disabled, reason) {
        if (!cb) { return; }
        const row = cb.closest(".opt-row");
        cb.disabled = disabled;
        if (disabled) {
            cb.checked = false;
            cb.title = reason;
            row?.classList.add("opt-disabled");
        } else {
            cb.title = "";
            row?.classList.remove("opt-disabled");
        }
    }
    function setAllChecked(checked) {
        for (const cb of configEl.querySelectorAll('input[type="checkbox"]:not(:disabled)')) {
            cb.checked = checked;
        }
        syncPreview();
        syncPresetActive(activeConfig);
    }
    function setGroupChecked(gi, cmdName, checked) {
        for (const cb of configEl.querySelectorAll('input[type="checkbox"]:not(:disabled)')) {
            if (cb.id.startsWith(`opt_${cmdName}_g${gi}_`)) { cb.checked = checked; }
        }
        syncPreview();
        syncPresetActive(activeConfig);
    }
    // Tooltips
    let activeTip = null;
    function attachTooltips() {
        for (const btn of configEl.querySelectorAll(".flag-tip-btn")) {
            btn.addEventListener("mouseenter", (e) => showTip(e.currentTarget));
            btn.addEventListener("focus", (e) => showTip(e.currentTarget));
            btn.addEventListener("mouseleave", hideTip);
            btn.addEventListener("blur", hideTip);
        }
    }
    function showTip(btn) {
        hideTip();
        const tip = document.createElement("div");
        tip.className = "flag-tooltip";
        tip.textContent = btn.dataset.tip;
        document.body.appendChild(tip);
        const r = btn.getBoundingClientRect();
        tip.style.left = `${Math.min(r.left, window.innerWidth - tip.offsetWidth - 12)}px`;
        tip.style.top = `${r.top - tip.offsetHeight - 6 + window.scrollY}px`;
        activeTip = tip;
    }
    function hideTip() {
        activeTip?.remove();
        activeTip = null;
    }
    // Args
    function buildArgs() {
        const grouped = {};
        const simple = [];
        for (const cb of configEl.querySelectorAll('input[type="checkbox"]:checked:not(:disabled)')) {
            const parts = cb.dataset.flag.split(" ");
            if (parts.length === 2 && parts[0].startsWith("-")) {
                const key = parts[0];
                if (!grouped[key]) { grouped[key] = []; }
                grouped[key].push(parts[1]);
            } else {
                simple.push(...parts);
            }
        }
        const args = [];
        for (const [key, vals] of Object.entries(grouped)) { args.push(key, ...vals); }
        args.push(...simple);
        for (const sel of configEl.querySelectorAll("select:not(:disabled)")) {
            if (sel.value) { args.push(...sel.value.split(" ")); }
        }
        return args;
    }
    function buildDisplayArgs(args) {
        const inject = config?.commands?.[activeCmd]?.inject_flags ?? [];
        const display = [...args];
        for (const f of inject) { if (!display.includes(f)) { display.push(f); } }
        return display;
    }
    function syncPreview() {
        if (!activeCmd || !config) { return; }
        if (activeConfig?.static) { prevEl.textContent = ""; return; }
        const script = config.commands[activeCmd].script;
        const display = buildDisplayArgs(buildArgs());
        const scriptPath = `tool/python/${script}`;
        prevEl.textContent = `$ ${[config.python, scriptPath, ...display].join(" ")}`;
    }
    // Generic confirm helper
    function askConfirm({ title, message, preview, okLabel, cancelLabel, onOk, onCancel }) {
        const titleEl = $("confirm-title");
        if (titleEl) { titleEl.textContent = title ?? "Confirm (Enter)"; }
        confirmMsg.textContent = message ?? "";
        if (preview) {
            confirmPreview.textContent = preview;
            confirmPreview.hidden = false;
        } else {
            confirmPreview.textContent = "";
            confirmPreview.hidden = true;
        }
        const okText = okLabel ?? "OK (Enter)";
        const cancelText = cancelLabel ?? "Cancel (ESC)";
        confirmOk.textContent = okText;
        confirmOk.title = okText;
        confirmCancel.textContent = cancelText;
        confirmCancel.title = cancelText;
        confirmDialog.showModal();
        confirmOk.focus();
        const cleanup = () => {
            confirmOk.removeEventListener("click", handleOk);
            confirmCancel.removeEventListener("click", handleCancel);
            confirmDialog.close();
        };
        const handleOk = () => { cleanup(); onOk?.(); };
        const handleCancel = () => { cleanup(); onCancel?.(); };
        confirmOk.addEventListener("click", handleOk);
        confirmCancel.addEventListener("click", handleCancel);
    }
    confirmDialog.addEventListener("click", (e) => {
        const rect = confirmDialog.getBoundingClientRect();
        const outside = e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom;
        if (outside) { confirmCancel.click(); }
    });
    // Run
    function executeRun(command, args) {
        if (autoClearEnabled && outEl.hasChildNodes()) {
            outEl.innerHTML = "";
            clearStatusBar();
            for (const key of Object.keys(cmdLineCounts)) { resetCmdBadge(key); }
        }
        lastClearedOutput = null;
        lastClearedBadges = null;
        lastClearedStatusBar = null;
        running = true;
        runningCmd = command;
        autoScroll = true;
        syncScrollBtn();
        syncButtons();
        setRunningBtn(command, true);
        ws.send(JSON.stringify({ action: "run", command, args }));
    }
    function setRunningBtn(cmdName, active) {
        for (const b of navEl.querySelectorAll(".cmd-btn")) {
            b.classList.toggle("running", active && b.dataset.cmd === cmdName);
        }
    }
    runBtn.addEventListener("click", () => {
        if (!activeCmd || ws?.readyState !== 1 || running) { return; }
        requestNotifyPermission();
        executeRun(activeCmd, buildArgs());
    });
    // Stop
    stopBtn.addEventListener("click", () => {
        if (ws?.readyState !== 1 || !running) { return; }
        ws.send(JSON.stringify({ action: "stop" }));
    });
    // Clear
    clearBtn.addEventListener("click", () => {
        if (!outEl.hasChildNodes()) { return; }
        askConfirm({
            title: "Clear output",
            message: "Clear all output? This cannot be undone.",
            okLabel: "Clear (Enter)",
            cancelLabel: "Cancel (ESC)",
            onOk: () => {
                lastClearedOutput = outEl.innerHTML;
                lastClearedBadges = { ...cmdLineCounts };
                lastClearedStatusBar = {
                    lines: sbLines.textContent,
                    cmd: sbCmd.textContent,
                    result: sbResult.textContent,
                    resultClass: sbResult.className,
                    duration: sbDuration.textContent,
                    progress: sbProgress.textContent,
                    progressClass: sbProgress.className,
                    time: sbTime.textContent,
                    timeLastRun: sbTime.dataset.lastrun ?? null,
                    timeTitle: sbTime.title,
                };
                outEl.innerHTML = "";
                document.title = BASE_TITLE;
                if (searchActive) { clearSearch(); }
                clearStatusBar();
                for (const key of Object.keys(cmdLineCounts)) { resetCmdBadge(key); }
                runBtn.title = "Run command (Ctrl+Enter)";
                if (activeCmd) { localStorage.removeItem(`toolkit-lastrun-${activeCmd}`); }
                syncButtons();
            },
        });
    });
    // Export
    function updateExportTooltip() {
        if (!outEl.hasChildNodes()) { exportBtn.title = "Export output as .txt"; return; }
        const now = new Date();
        const ts = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}_${pad(now.getHours())}-${pad(now.getMinutes())}-${pad(now.getSeconds())}`;
        exportBtn.title = `Export as toolkit-output-${ts}.txt`;
    }
    exportBtn.addEventListener("mouseenter", updateExportTooltip);
    exportBtn.addEventListener("focus", updateExportTooltip);
    exportBtn.addEventListener("click", () => {
        if (!outEl.hasChildNodes()) { return; }
        const lines = [...outEl.querySelectorAll("div")]
            .map(d => d.dataset.raw ?? d.textContent)
            .join("\n");
        if (!lines.trim()) { return; }
        const now = new Date();
        const ts = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}_${pad(now.getHours())}-${pad(now.getMinutes())}-${pad(now.getSeconds())}`;
        const filename = `toolkit-output-${ts}.txt`;
        askConfirm({
            title: "Export output",
            message: `Download the output as "${filename}"?`,
            okLabel: "Download (Enter)",
            cancelLabel: "Cancel (ESC)",
            onOk: () => {
                const blob = new Blob([lines], { type: "text/plain;charset=utf-8" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = filename;
                a.click();
                URL.revokeObjectURL(url);
            },
        });
    });
    copyBtn.addEventListener("click", () => {
        if (!outEl.hasChildNodes()) { return; }
        const text = [...outEl.querySelectorAll("div")]
            .map(d => d.dataset.raw ?? d.textContent)
            .filter((l, i, arr) => l.trim() || (arr[i - 1]?.trim()))
            .join("\n");
        navigator.clipboard.writeText(text).then(() => {
            const prev = copyBtn.innerHTML;
            copyBtn.classList.add("copied");
            copyBtn.textContent = "Copied!";
            setTimeout(() => { copyBtn.classList.remove("copied"); copyBtn.innerHTML = prev; }, 1800);
        }).catch(() => {
            const prev = copyBtn.innerHTML;
            copyBtn.textContent = "Failed";
            setTimeout(() => { copyBtn.innerHTML = prev; }, 1500);
        });
    });
    // Output search
    let searchActive = false, searchQuery = "", searchMatches = [], searchIndex = -1;
    function showSearch() {
        searchBar.classList.add("visible");
        searchToggleBtn.classList.add("active");
        searchActive = true;
        searchInput.focus();
        searchInput.select();
    }
    function hideSearch() {
        searchBar.classList.remove("visible");
        searchToggleBtn?.classList.remove("active");
        searchActive = false;
        clearSearch();
    }
    function clearSearch() {
        searchQuery = "";
        searchMatches = [];
        searchIndex = -1;
        searchInput.value = "";
        restorePlainText();
        searchCount.textContent = "";
    }
    function restorePlainText() {
        for (const div of outEl.querySelectorAll("div")) {
            const raw = div.dataset.raw;
            if (raw !== undefined) {
                div.textContent = raw;
                delete div.dataset.raw;
            }
        }
    }
    // Escapes special regex characters using String.raw to avoid backslash escaping issues
    const escRegex = s => s.replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`);
    function escHtml(s) {
        return s.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
    }
    function renderSearchHighlights() {
        searchMatches = [];
        if (!searchQuery) {
            restorePlainText();
            searchCount.textContent = "";
            return;
        }
        const re = new RegExp(escRegex(searchQuery), "gi");
        for (const div of outEl.querySelectorAll("div")) {
            if (!div.dataset.raw) { div.dataset.raw = div.textContent; }
            const raw = div.dataset.raw;
            const matches = [...raw.matchAll(re)];
            if (!matches.length) { div.textContent = raw; continue; }
            let html = "", last = 0;
            for (const m of matches) {
                html += `${escHtml(raw.slice(last, m.index))}<mark class="sh" data-mi="${searchMatches.length}">${escHtml(m[0])}</mark>`;
                searchMatches.push(div);
                last = m.index + m[0].length;
            }
            div.innerHTML = `${html}${escHtml(raw.slice(last))}`;
        }
        if (searchMatches.length > 0 && searchIndex < 0) { searchIndex = 0; }
        updateSearchCount();
        updateActiveHighlight();
    }
    function rehighlightLine(div) {
        if (!searchQuery) { return; }
        const re = new RegExp(escRegex(searchQuery), "gi");
        if (!div.dataset.raw) { div.dataset.raw = div.textContent; }
        const raw = div.dataset.raw;
        const matches = [...raw.matchAll(re)];
        if (!matches.length) { return; }
        let html = "", last = 0;
        for (const m of matches) {
            html += `${escHtml(raw.slice(last, m.index))}<mark class="sh" data-mi="${searchMatches.length}">${escHtml(m[0])}</mark>`;
            searchMatches.push(div);
            last = m.index + m[0].length;
        }
        div.innerHTML = `${html}${escHtml(raw.slice(last))}`;
        updateSearchCount();
    }
    function updateSearchCount() {
        searchCount.textContent = searchMatches.length
            ? `${Math.max(searchIndex + 1, 1)} / ${searchMatches.length}`
            : "No results";
    }
    function updateActiveHighlight() {
        for (const mark of outEl.querySelectorAll("mark.sh")) { mark.classList.remove("sh-active"); }
        if (searchIndex < 0 || searchIndex >= searchMatches.length) { return; }
        const first = searchMatches[searchIndex].querySelector("mark.sh");
        if (first) {
            first.classList.add("sh-active");
            first.scrollIntoView({ block: "center", behavior: "smooth" });
        }
        updateSearchCount();
    }
    function searchStep(dir) {
        if (!searchMatches.length) { return; }
        searchIndex = (searchIndex + dir + searchMatches.length) % searchMatches.length;
        updateActiveHighlight();
    }
    let searchDebounce = null;
    searchInput.addEventListener("input", () => {
        searchQuery = searchInput.value;
        searchIndex = -1;
        clearTimeout(searchDebounce);
        searchDebounce = setTimeout(renderSearchHighlights, 120);
    });
    searchNext.addEventListener("click", () => searchStep(+1));
    searchPrev.addEventListener("click", () => searchStep(-1));
    searchClose.addEventListener("click", hideSearch);
    searchToggleBtn.addEventListener("click", () => {
        if (searchActive) { hideSearch(); }
        else showSearch();
    });
    searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); searchStep(e.shiftKey ? -1 : +1); }
        if (e.key === "Escape") { hideSearch(); }
    });
    function setRunBtnState(isRunning) {
        const tpl = isRunning ? "tpl-icon-run-spin" : "tpl-icon-run-idle";
        const oldIcon = $("run-icon");
        if (!oldIcon) { return; }
        const newIcon = $(tpl).content.firstElementChild.cloneNode(true);
        newIcon.id = "run-icon";
        oldIcon.replaceWith(newIcon);
    }
    // Buttons sync
    function syncButtons() {
        const hasOut = outEl.hasChildNodes();
        scrollTopBtn.disabled = !hasOut;
        scrollBotBtn.disabled = !hasOut;
        runBtn.disabled = running || !activeCmd || !!activeConfig?.static;
        stopBtn.disabled = !running;
        clearBtn.disabled = running || !hasOut;
        exportBtn.disabled = !hasOut;
        copyBtn.disabled = !hasOut;
        searchToggleBtn.disabled = !hasOut;
        undoBtn.disabled = !lastClearedOutput || running;
        spinnerEl.classList.toggle("active", running);
        setRunBtnState(running);
        collapseConfigBtn.disabled = !activeCmd;
        collapseOutBtn.disabled = !activeCmd;
        filterToggleBtn.disabled = !hasOut;
    }
    scrollTopBtn.addEventListener("click", () => { outEl.scrollTop = 0; autoScroll = false; syncScrollBtn(); });
    scrollBotBtn.addEventListener("click", () => { outEl.scrollTop = outEl.scrollHeight; autoScroll = true; syncScrollBtn(); });
    // Keyboard shortcuts
    function handleEscape() {
        if (confirmDialog.open) { confirmCancel.click(); return; }
        if (searchActive) { hideSearch(); return; }
        if (running && ws?.readyState === 1) ws.send(JSON.stringify({ action: "stop" }));
    }
    function handleCtrlEnter() {
        if (confirmDialog.open) { confirmOk.click(); return; }
        runBtn.click();
    }
    function handleCtrlL() {
        if (!clearBtn.disabled) { clearBtn.click(); }
    }
    function handleCtrlF() {
        if (outEl.hasChildNodes()) { showSearch(); }
    }
    function handleCtrlB() {
        sidebarCollapseBtn.click();
    }
    function performUndo() {
        if (!lastClearedOutput || running) { return; }
        outEl.innerHTML = lastClearedOutput;
        lastClearedOutput = null;
        if (lastClearedStatusBar) {
            sbLines.textContent = lastClearedStatusBar.lines;
            sbCmd.textContent = lastClearedStatusBar.cmd;
            sbResult.textContent = lastClearedStatusBar.result;
            sbResult.className = lastClearedStatusBar.resultClass;
            sbDuration.textContent = lastClearedStatusBar.duration;
            sbProgress.textContent = lastClearedStatusBar.progress;
            sbProgress.className = lastClearedStatusBar.progressClass;
            sbTime.textContent = lastClearedStatusBar.time;
            sbTime.title = lastClearedStatusBar.timeTitle;
            if (lastClearedStatusBar.timeLastRun) { sbTime.dataset.lastrun = lastClearedStatusBar.timeLastRun; }
            lastClearedStatusBar = null;
        }
        if (lastClearedBadges) {
            for (const [key, count] of Object.entries(lastClearedBadges)) {
                cmdLineCounts[key] = count;
                updateCmdBadge(key);
            }
            lastClearedBadges = null;
        } else if (activeCmd) {
            cmdLineCounts[activeCmd] = outEl.querySelectorAll("div").length;
            updateCmdBadge(activeCmd);
        }
        updateSbLines();
        if (searchActive && searchQuery) { renderSearchHighlights(); }
        if (activeCmd) { updateRunBtnTooltip(activeCmd); }
        syncButtons();
        undoBtn.classList.add("restored");
        setTimeout(() => undoBtn.classList.remove("restored"), 600);
    }
    function handleCtrlZ() { performUndo(); }
    undoBtn.addEventListener("click", performUndo);
    const SHORTCUTS = [
        { key: "Escape", handler: handleEscape },
        { key: "Enter", ctrl: true, handler: handleCtrlEnter },
        { key: "l", ctrl: true, handler: handleCtrlL },
        { key: "f", ctrl: true, handler: handleCtrlF },
        { key: "F", ctrl: true, shift: true, handler: () => { if (!filterToggleBtn.disabled) toggleFilter(); } },
        { key: "B", ctrl: true, shift: true, handler: () => { if (!collapseConfigBtn.disabled) collapseConfigBtn.click(); } },
        { key: "b", ctrl: true, alt: true, handler: () => { if (!collapseOutBtn.disabled) collapseOutBtn.click(); } },
        { key: "b", ctrl: true, handler: handleCtrlB },
        { key: "z", ctrl: true, handler: handleCtrlZ },
    ];
    document.addEventListener("keydown", (e) => {
        if (document.activeElement?.classList.contains("notes-textarea")) { return; }
        for (const s of SHORTCUTS) {
            const ctrlMatch = !s.ctrl || e.ctrlKey || e.metaKey;
            const shiftMatch = !!s.shift === e.shiftKey;
            const altMatch = !!s.alt === e.altKey;
            const keyMatch = e.key.toLowerCase() === s.key.toLowerCase();
            if (keyMatch && ctrlMatch && shiftMatch && altMatch) {
                if (s.key !== "Escape") { e.preventDefault(); }
                s.handler();
                return;
            }
        }
    });
    // Reset service
    const restartBtn = $("restart-btn");
    restartBtn.addEventListener("click", () => {
        askConfirm({
            title: "Restart server",
            message: "Restart the toolkit server? The page will reconnect automatically.",
            okLabel: "Restart (Enter)",
            cancelLabel: "Cancel (ESC)",
            onOk: () => {
                fetch("/api/restart", { method: "POST" })
                    .then(r => r.json())
                    .then(d => {
                        if (!d.ok) { appendLine(`⚠ Cannot restart: ${d.reason}`, "line-warn"); }
                    })
                    .catch(() => { });
            }
        });
    });
    // Project switcher
    const projectSwitcher = $("project-switcher");
    function refreshProjectSwitcher() {
        if (!projectSwitcher) { return; }
        fetch("/api/projects").then(r => r.json()).then(d => {
            const list = d?.projects || [];
            if (list.length < 2) { projectSwitcher.hidden = true; return; }
            projectSwitcher.innerHTML = "";
            list.forEach(p => {
                const opt = document.createElement("option");
                opt.value = p.id;
                opt.textContent = p.name || p.id;
                if (p.active) { opt.selected = true; }
                projectSwitcher.appendChild(opt);
            });
            projectSwitcher.hidden = false;
        }).catch(() => { });
    }
    if (projectSwitcher) {
        projectSwitcher.addEventListener("change", () => {
            const id = projectSwitcher.value;
            fetch("/api/projects/select", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ id })
            })
                .then(r => r.json())
                .then(res => {
                    if (res?.ok) { location.reload(); }
                    else { appendLine(`⚠ Cannot switch: ${res?.reason || "error"}`, "line-warn"); }
                })
                .catch(() => { appendLine("⚠ Switch failed", "line-warn"); });
        });
    }
    // Init
    function tick() {
        if (sbTime.dataset.lastrun) { return; }
        const now = new Date();
        const mon = MONTHS[now.getMonth()];
        const day = String(now.getDate()).padStart(2, "0");
        sbTime.textContent = `${mon} ${day} · ${formatTime(now)}`;
    }
    function startClock() {
        if (clockTimer) { return; }
        tick();
        clockTimer = setInterval(tick, 1000);
    }
    function init() {
        document.body.classList.add("welcome-mode");
        startClock();
        initTheme();
        connectWs();
        syncButtons();
        syncConfigCollapse();
        syncSidebarCollapse();
        syncOutputCollapse();
        syncScrollBtn();
        requestNotifyPermission();
        syncAutoClearBtn();
        syncSoundBtn();
    }
    init();
}();
