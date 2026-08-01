function $(id) { return document.getElementById(id); }

let ws = null;

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (evt) => render(JSON.parse(evt.data));
  ws.onclose = () => setTimeout(connect, 1000);
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
  renderRawLog(state);
}

$("reconnect-btn").onclick = async () => {
  await fetch("/api/reconnect", { method: "POST" });
};

connect();
