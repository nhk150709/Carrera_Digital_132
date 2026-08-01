function $(id) { return document.getElementById(id); }

let ws = null;

// Mirrors app/cu/protocol.py's button ID constants -- see that file's
// docstrings for what each one does on real hardware.
const BUTTONS = [
  { id: 2, label: "START / ENTER" },
  { id: 1, label: "PACE CAR / ESC" },
  { id: 5, label: "SPEED" },
  { id: 6, label: "BRAKE" },
  { id: 7, label: "FUEL" },
  { id: 8, label: "CODE" },
];
const ADDRESSES = [0, 1, 2, 3, 4, 5, 6, 7];

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (evt) => render(JSON.parse(evt.data));
  ws.onclose = () => setTimeout(connect, 1000);
}

async function post(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await resp.json().catch(() => ({}));
  if (!data.ok) {
    console.warn("command rejected:", url, body, data.error);
  }
  return data;
}

function renderConnBadge(state) {
  const badge = $("conn-badge");
  const isMock = state.backend && state.backend.startsWith("MOCK");
  if (isMock) {
    badge.textContent = "MOCK (no real hardware)";
    badge.className = "badge mock";
  } else if (state.connected) {
    badge.textContent = "CONNECTED";
    badge.className = "badge connected";
  } else {
    badge.textContent = "DISCONNECTED";
    badge.className = "badge disconnected";
  }
}

function renderBackendPanel(state) {
  $("backend-text").textContent = state.backend || "-";
  $("device-text").textContent = state.requested_device || "-";
  $("cu-connected-text").textContent = state.connected ? "yes" : "no";
  $("connect-attempts-text").textContent = state.connect_attempts;
  $("controller-writes-text").textContent = state.controller_writes_allowed
    ? "ALLOWED (CARRERA_RMS_CU_ALLOW_CONTROLLER_WRITES=1)"
    : "BLOCKED (set CARRERA_RMS_CU_ALLOW_CONTROLLER_WRITES=1 to allow testing them)";
  const errRow = $("last-error-row");
  if (state.last_error) {
    $("last-error-text").textContent = state.last_error;
    errRow.style.display = "";
  } else {
    errRow.style.display = "none";
  }
}

function renderStatus(state) {
  const s = state.status;
  const tbody = document.querySelector("#fuel-pit-table tbody");
  tbody.innerHTML = "";
  if (!s) {
    $("start-value").textContent = "-";
    $("start-label").textContent = "-";
    $("mode-value").textContent = "-";
    $("display-value").textContent = "-";
    return;
  }
  s.fuel.forEach((fuelRaw, addr) => {
    const pit = s.pit[addr];
    const tr = document.createElement("tr");
    if (pit) tr.className = "pit-active";
    const pct = Math.round((fuelRaw / 15) * 100);
    tr.innerHTML = `<td>${addr}</td><td>${fuelRaw}</td><td>${pct}%</td><td>${pit ? "IN PIT" : "-"}</td>`;
    tbody.appendChild(tr);
  });
  $("start-value").textContent = s.start;
  $("start-label").textContent = s.start_label;
  $("mode-value").textContent = `${s.mode} (${s.mode_flags.length ? s.mode_flags.join(", ") : "none set"})`;
  $("display-value").textContent = s.display;
}

function renderTimerLog(state) {
  const tbody = document.querySelector("#timer-table tbody");
  tbody.innerHTML = "";
  state.timer_log.slice(0, 100).forEach((e) => {
    const tr = document.createElement("tr");
    const wallTime = new Date(e.time * 1000).toLocaleTimeString();
    tr.innerHTML = `<td>${wallTime}</td><td>${e.address}</td><td>${e.sector_label}</td><td>${e.timestamp.toFixed(3)}</td>`;
    tbody.appendChild(tr);
  });
}

function renderCommandLog(state) {
  const el = $("command-log");
  el.innerHTML = state.command_log.slice(0, 100).map((e) => {
    const t = new Date(e.time * 1000).toLocaleTimeString();
    const status = e.ok ? '<span class="cmd-ok">OK</span>' : `<span class="cmd-err">REJECTED: ${escapeHtml(e.error || "")}</span>`;
    return `<div>[${t}] ${escapeHtml(e.command)} -- ${status}</div>`;
  }).join("");
}

function renderRawLog(state) {
  const el = $("raw-log");
  el.innerHTML = state.raw_log.slice(0, 200).map((e) => {
    const t = new Date(e.time * 1000).toLocaleTimeString();
    return `<div>[${t}] ${e.logger}: ${escapeHtml(e.message)}</div>`;
  }).join("");
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function render(state) {
  renderConnBadge(state);
  renderBackendPanel(state);
  renderStatus(state);
  renderTimerLog(state);
  renderCommandLog(state);
  renderRawLog(state);
}

function buildWriteTable() {
  const tbody = document.querySelector("#write-table tbody");
  tbody.innerHTML = "";
  ADDRESSES.forEach((addr) => {
    const tr = document.createElement("tr");
    const note = addr === 6 ? " (autonomous)" : addr === 7 ? " (pace car)" : "";
    tr.innerHTML = `
      <td>${addr}${note}</td>
      <td><input type="number" min="0" max="15" value="0" id="speed-${addr}" style="width:3.5rem"></td>
      <td><button data-kind="speed" data-addr="${addr}">Send</button></td>
      <td><input type="number" min="0" max="15" value="0" id="brake-${addr}" style="width:3.5rem"></td>
      <td><button data-kind="brake" data-addr="${addr}">Send</button></td>
      <td><input type="number" min="0" max="15" value="0" id="fuel-${addr}" style="width:3.5rem"></td>
      <td><button data-kind="fuel" data-addr="${addr}">Send</button></td>
    `;
    tbody.appendChild(tr);
  });
  tbody.querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => {
      const addr = parseInt(btn.dataset.addr, 10);
      const kind = btn.dataset.kind;
      const value = parseInt($(`${kind}-${addr}`).value, 10) || 0;
      const url = kind === "speed" ? "/api/cu/speed" : kind === "brake" ? "/api/cu/brake" : "/api/cu/fuel";
      post(url, { address: addr, value });
    };
  });
}

function buildButtonRow() {
  const el = $("button-row");
  el.innerHTML = "";
  BUTTONS.forEach(({ id, label }) => {
    const btn = document.createElement("button");
    btn.textContent = `Press ${label} (id=${id})`;
    btn.onclick = () => post("/api/cu/press", { button_id: id });
    el.appendChild(btn);
  });
}

function buildIgnoreChecks() {
  const el = $("ignore-checks");
  el.innerHTML = "";
  ADDRESSES.forEach((addr) => {
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox" id="ignore-${addr}"> ${addr}`;
    el.appendChild(label);
  });
}

function wireStaticControls() {
  buildWriteTable();
  buildButtonRow();
  buildIgnoreChecks();

  $("reconnect-btn").onclick = () => post("/api/reconnect");

  $("ignore-send-btn").onclick = () => {
    let mask = 0;
    ADDRESSES.forEach((addr) => {
      if ($(`ignore-${addr}`).checked) mask |= (1 << addr);
    });
    post("/api/cu/ignore", { mask });
  };

  $("reset-cu-btn").onclick = () => post("/api/cu/reset");
  $("clear-position-btn").onclick = () => post("/api/cu/clear_position");
  $("pos-send-btn").onclick = () => post("/api/cu/position", {
    address: parseInt($("pos-addr").value, 10) || 0,
    position: parseInt($("pos-value").value, 10) || 1,
  });
  $("lap-send-btn").onclick = () => post("/api/cu/lap", { value: parseInt($("lap-value").value, 10) || 0 });
}

wireStaticControls();
connect();
