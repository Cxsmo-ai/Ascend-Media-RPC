
const API_STATE = "/api/state";
const API_CMD = "/api/command";
const API_SET = "/api/settings";

let configLoaded = false;

async function fetchState() {
    try {
        const res = await fetch(API_STATE);
        if (!res.ok) return;
        const data = await res.json();

        // RPC is Connected if we got data
        const rpcEl = document.getElementById("rpc-status");
        if (rpcEl) {
            rpcEl.textContent = "RPC: CONNECTED";
            rpcEl.classList.remove("disconnected");
            rpcEl.classList.add("connected");
        }

        updateUI(data);

        // Sync Inputs (Once or if changed)
        if (data.config && !configLoaded) {
            document.getElementById("inp-adb-host").value = data.config.adb_host;
            document.getElementById("inp-tmdb-key").value = data.config.tmdb_key;
            document.getElementById("chk-show-name").checked = data.config.show_device;
            document.getElementById("chk-profanity").checked = data.config.profanity;
            configLoaded = true;
        }

    } catch (e) {
        console.error("Poll error", e);
        // RPC Error
        const rpcEl = document.getElementById("rpc-status");
        if (rpcEl) {
            rpcEl.textContent = "RPC: DISCONNECTED";
            rpcEl.classList.remove("connected");
            rpcEl.classList.add("disconnected");
        }
    }
}

async function saveSettings(action) {
    const payload = {
        action: action,
        adb_host: document.getElementById("inp-adb-host").value,
        tmdb_key: document.getElementById("inp-tmdb-key").value,
        show_device: document.getElementById("chk-show-name").checked,
        profanity: document.getElementById("chk-profanity").checked
    };

    try {
        await fetch(API_SET, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (action === 'connect') alert("Connecting to ADB...");
    } catch (e) {
        alert("Failed to save settings");
    }
}

// State Cache
let currentPosition = 0;
let currentDuration = 0;
let currentMeta = { imdb: "", s: 0, e: 0 };

async function launchLogin() {
    try {
        await fetch("/api/intro_login", { method: "POST" });
        alert("Browser launched on Host PC. Please login there.");
    } catch (e) { alert("Error launching login"); }
}

async function scanDevices() {
    const btn = document.getElementById("btn-scan");
    const originalText = btn.innerText;
    btn.innerText = "Scanning...";
    btn.disabled = true;

    try {
        const res = await fetch("/api/scan", { method: "POST" });
        const data = await res.json();

        if (data.devices && data.devices.length > 0) {
            // Populate select
            const sel = document.getElementById("sel-devices");
            sel.innerHTML = '<option value="">Select Device...</option>';
            data.devices.forEach(d => {
                const opt = document.createElement("option");
                opt.value = d.ip;
                opt.innerText = `${d.name || "Unknown"} (${d.ip})`;
                sel.appendChild(opt);
            });
            sel.style.display = "block"; // Show dropdown
            alert(`Found ${data.devices.length} devices!`);
        } else {
            alert("No devices found.");
        }
    } catch (e) {
        alert("Scan failed: " + e);
    }

    btn.innerText = originalText;
    btn.disabled = false;
}

function selectDevice() {
    const sel = document.getElementById("sel-devices");
    if (sel.value) {
        document.getElementById("inp-adb-host").value = sel.value;
    }
}

function captureTime(type) {
    const sec = (currentPosition / 1000).toFixed(1);
    document.getElementById(`inp-${type}`).value = sec;
}

async function submitIntro() {
    const start = document.getElementById("inp-start").value;
    const end = document.getElementById("inp-end").value;

    if (!start || !end || !currentMeta.imdb) {
        alert("Missing Data! Please play a show and capture times.");
        return;
    }

    // UI Feedback
    const btn = document.querySelector(".btn-full.primary");
    const oldText = btn.innerText;
    btn.innerText = "Submitting...";
    btn.disabled = true;

    try {
        const payload = {
            imdb_id: currentMeta.imdb,
            season: currentMeta.s,
            episode: currentMeta.e,
            start: parseFloat(start),
            end: parseFloat(end)
        };

        const res = await fetch("/api/submit_intro", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        alert("Result: " + (data.result || data.error));

    } catch (e) {
        alert("Submission Failed: " + e);
    }

    btn.innerText = oldText;
    btn.disabled = false;
}

function updateUI(data) {
    // ... (existing code) ...
    // Store for capture
    currentPosition = data.position || 0;
    currentDuration = data.duration || 0;

    // Update Meta
    if (data.meta) {
        currentMeta = {
            imdb: data.meta.imdb,
            s: data.meta.s,
            e: data.meta.e
        };
        // Update Read-only fields
        document.getElementById("inp-imdb").value = data.meta.imdb || "";
        document.getElementById("inp-se").value = (data.meta.s && data.meta.e) ? `S${data.meta.s}E${data.meta.e}` : "";
    }

    // Try to parse metadata from title? 
    // Ideally app should send this separately.
    // For now we assume the app updates 'shared_state' with explicit metadata, 
    // BUT we didn't add that explicit metadata to shared_state yet!
    // We only added 'title'.
    // Let's rely on manual input or basic parsing for now, 
    // OR we need to add imdb_id to shared_state in app.py.

    // Actually, let's just update based on shared_state if it exist
    // Update: I missed adding imdb_id to shared_state in app.py step!
    // I will add it in next tool call if needed.

    // Connection (Device Status)
    const statusEl = document.getElementById("connection-status");
    if (statusEl) {
        if (data.connected) {
            statusEl.textContent = "Device: CONNECTED";
            statusEl.classList.remove("disconnected");
            statusEl.classList.add("connected");
        } else {
            statusEl.textContent = "Device: DISCONNECTED";
            statusEl.classList.remove("connected");
            statusEl.classList.add("disconnected");
        }
    }

    document.getElementById("device-name").textContent = data.device;

    // Media
    document.getElementById("media-title").textContent = data.title || "Ready to Play";
    document.getElementById("media-subtitle").textContent = data.subtitle || "Waiting for device...";

    // Progress
    const pct = (data.progress * 100).toFixed(1) + "%";
    document.getElementById("progress-fill").style.width = pct;

    // Skip Status
    const skipEl = document.getElementById("skip-status");
    if (skipEl && data.skip_status) {
        skipEl.innerText = data.skip_status.msg || "";
        skipEl.style.color = data.skip_status.color || "gray";
    }

    // Image
    const imgEl = document.getElementById("poster-img");
    if (data.image_url) {
        if (imgEl.src !== data.image_url) imgEl.src = data.image_url;
        imgEl.classList.remove("hidden");
    } else {
        imgEl.classList.add("hidden");
    }

    // Toggle
    document.getElementById("chk-auto-skip").checked = data.auto_skip; // Read-only view of server state
}

async function sendCommand(cmd) {
    // Optimistic UI updates
    if (cmd === 'toggle_skip') {
        const chk = document.getElementById("chk-auto-skip");
        chk.checked = !chk.checked;
    }

    try {
        await fetch(API_CMD, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command: cmd })
        });
        // Immediately fetch state to confirm
        setTimeout(fetchState, 200);
    } catch (e) {
        console.error("Command error", e);
    }
}

// Poll Loop
setInterval(fetchState, 1000);
fetchState(); // Init
