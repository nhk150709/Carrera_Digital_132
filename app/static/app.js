const ADDRESSES = [0, 1, 2, 3, 4, 5, 6, 7];

let ws = null;
let latestState = null;
let keys = { throttle: false, brake: false, lane: false, stop: false, overtake: false };
let pedals = { throttle: false, brake: false };
let overtakeHeld = false;
let lastEventSeq = 0;

function $(id) { return document.getElementById(id); }

function buildLights(container) {
  container.innerHTML = "";
  for (let i = 1; i <= 5; i++) {
    const div = document.createElement("div");
    div.className = "light";
    div.dataset.n = i;
    container.appendChild(div);
  }
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => { $("conn-dot").classList.add("connected"); $("conn-text").textContent = "connected"; };
  ws.onclose = () => {
    $("conn-dot").classList.remove("connected");
    $("conn-text").textContent = "disconnected";
    setTimeout(connect, 1000);
  };
  ws.onmessage = (evt) => {
    latestState = JSON.parse(evt.data);
    render(latestState);
  };
}

function fmt(t) { return t === null || t === undefined ? "-" : t.toFixed(2); }

function renderStartLights(container, phase) {
  const isGo = phase === "GO";
  const litCount = phase && /^L[1-5]$/.test(phase) ? parseInt(phase[1], 10) : 0;
  container.querySelectorAll(".light").forEach((el) => {
    const n = parseInt(el.dataset.n, 10);
    el.classList.toggle("lit", !isGo && n <= litCount);
    el.classList.toggle("go", isGo);
  });
}

function renderStopBanner(state) {
  const banner = $("stop-banner");
  if (state.state === "paused") {
    const addr = state.last_stop_triggered_by;
    const car = addr !== null && addr !== undefined ? state.cars[String(addr)] : null;
    banner.textContent = car
      ? `RACE STOPPED -- triggered by ${car.name || "Car " + car.address}`
      : "RACE STOPPED";
    banner.classList.add("show");
  } else {
    banner.classList.remove("show");
  }
}

function renderSafetyCarBanner(state) {
  const banner = $("safety-car-banner");
  if (state.safety_car && state.safety_car.active) {
    banner.textContent = state.safety_car.physically_present
      ? "SAFETY CAR DEPLOYED -- pace car on track, field capped"
      : "VIRTUAL SAFETY CAR -- field speed capped";
    banner.classList.add("show");
  } else {
    banner.classList.remove("show");
  }
}

function renderForecast(state) {
  const el = $("forecast-list");
  el.innerHTML = "";
  (state.weather_forecast || []).forEach((f) => {
    const span = document.createElement("span");
    span.className = "badge";
    span.textContent = `Lap ${f.lap}: ${f.predicted_level} (${Math.round(f.confidence * 100)}% confidence)`;
    el.appendChild(span);
  });
  if (!state.weather_forecast || state.weather_forecast.length === 0) {
    el.textContent = "No forecast set -- weather stays fixed until you generate one.";
  }
}

function renderPersonalPanel(state) {
  const addr = $("my-car-select").value;
  const car = addr !== undefined && addr !== "" ? state.cars[addr] : null;

  const banner = $("personal-overtake-banner");
  const status = $("overtake-status");
  const btn = $("overtake-btn");
  const pitBtn = $("pit-toggle-btn");
  const ghostEl = $("ghost-delta-display");

  if (!car) {
    banner.classList.remove("show");
    status.textContent = "";
    return;
  }

  if (car.overtake_active) {
    banner.classList.add("show");
    status.textContent = "Boost active!";
    btn.disabled = true;
  } else if (car.overtake_cooldown_remaining > 0) {
    banner.classList.remove("show");
    status.textContent = `Cooldown: ${car.overtake_cooldown_remaining.toFixed(1)}s`;
    btn.disabled = true;
  } else {
    banner.classList.remove("show");
    status.textContent = "Push to pass ready";
    btn.disabled = false;
  }

  pitBtn.textContent = car.in_pit ? "Exit Pit" : "Enter Pit";

  if (car.ghost_delta === null || car.ghost_delta === undefined) {
    ghostEl.textContent = "";
    ghostEl.className = "";
  } else {
    const d = car.ghost_delta;
    ghostEl.textContent = `Ghost delta: ${d > 0 ? "+" : ""}${d.toFixed(2)}s`;
    ghostEl.className = d > 0 ? "behind" : "ahead";
  }
}

function render(state) {
  $("state-badge").textContent = state.state;
  renderStartLights($("start-lights"), state.start_phase);
  renderStartLights($("personal-start-lights"), state.start_phase);
  renderStopBanner(state);
  renderSafetyCarBanner(state);
  $("cu-status-raw").textContent = state.cu_status
    ? JSON.stringify(state.cu_status, null, 2)
    : "not connected / no Status seen yet";
  renderForecast(state);

  const rankBody = $("ranking-body");
  rankBody.innerHTML = "";
  state.rankings.forEach((r) => {
    const tr = document.createElement("tr");
    if (r.position === 1) tr.classList.add("leader-row");
    tr.innerHTML = `<td>${r.position}</td><td>${r.name || ("Car " + r.address)}${r.jump_start ? ' <span class="jump">JUMP</span>' : ""}</td>` +
      `<td>${r.lap_count}${r.laps_down ? " (-" + r.laps_down + "lap)" : ""}</td>` +
      `<td>${fmt(r.best_lap)}</td><td>${fmt(r.last_lap)}</td><td>${fmt(r.delta_vs_best)}</td>` +
      `<td>${fmt(r.gap_to_leader)}</td><td>${r.penalty_seconds ? "+" + r.penalty_seconds + "s" : "-"}</td>`;
    rankBody.appendChild(tr);
  });

  const grid = $("car-grid");
  grid.innerHTML = "";
  const selects = [$("my-car-select"), $("strategy-car-select")];
  const prevSelected = selects.map((s) => s.value);
  selects.forEach((s) => { s.innerHTML = ""; });

  ADDRESSES.forEach((addr) => {
    const car = state.cars[String(addr)];
    if (!car) return;

    selects.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = addr;
      opt.textContent = `${addr} - ${car.name || "(unnamed)"}${addr === 6 ? " [autonomous]" : addr === 7 ? " [pace car]" : ""}`;
      s.appendChild(opt);
    });

    const card = document.createElement("div");
    card.className = "car-card";
    if (car.overtake_active) card.classList.add("overtake-active");
    if (car.broken_down) card.classList.add("broken-down");
    card.innerHTML = `
      <h3>${car.name || "Car " + addr} <span class="addr">#${addr} ${car.compound}</span></h3>
      <div>Controller: ${car.controller_id || "-"} ${car.jump_start ? '<span class="jump">JUMP START</span>' : ""}</div>
      <div>Lap ${car.lap_count} - Best ${fmt(car.best_lap)}s - Penalty ${car.penalty_seconds}s</div>
      ${car.controller_id ? `
      <div>Fuel ${Math.round(car.fuel)}%</div>
      <div class="bar fuel"><div style="width:${car.fuel}%"></div></div>
      <div>Tyre wear ${Math.round(car.tyre_wear)}%</div>
      <div class="bar tyre"><div style="width:${car.tyre_wear}%"></div></div>
      <div>Throttle ${Math.round(car.throttle * 100)}%</div>
      <div class="bar fuel"><div style="width:${car.throttle * 100}%; background:#2ea043"></div></div>
      <div>Brake ${Math.round(car.brake * 100)}%</div>
      <div class="bar fuel"><div style="width:${car.brake * 100}%; background:#da3633"></div></div>
      ` : `
      <div style="color:var(--muted); font-size:0.8rem">No controller assigned -- fuel/tyre/throttle
      simulation only runs for cars driven through this app (assign one below).
      Lap timing still works regardless, from the CU's own sensors.</div>
      `}
      <div>${car.in_pit ? "IN PIT" : ""} ${car.recording ? "REC" : ""} ${car.broken_down ? "BROKEN DOWN" : ""}</div>
    `;
    grid.appendChild(card);
  });
  selects.forEach((s, i) => { if (prevSelected[i]) s.value = prevSelected[i]; });

  renderPersonalPanel(state);

  const pacePlaying = state.pace_car && state.pace_car.active;
  $("pace-play").disabled = pacePlaying;

  if (state.events && state.events.length && window.CarreraSound) {
    window.CarreraSound.handleEvents(state.events);
  }
}

async function post(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!resp.ok) console.error(url, resp.status, await resp.text());
  return resp;
}

function sendInput() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const throttle = (keys.throttle || pedals.throttle) ? 1.0 : 0.0;
  const brake = (keys.brake || pedals.brake) ? 1.0 : 0.0;
  ws.send(JSON.stringify({
    type: "input",
    controller_id: $("my-controller-id").value || "player1",
    throttle, brake,
    lane_change: keys.lane,
    stop_pressed: keys.stop,
    overtake_pressed: keys.overtake || overtakeHeld,
  }));
}

function setupKeyboard() {
  window.addEventListener("keydown", (e) => {
    if (e.repeat) return;
    if (e.key === "w" || e.key === "ArrowUp") keys.throttle = true;
    if (e.key === "s" || e.key === "ArrowDown") keys.brake = true;
    if (e.key === "a") keys.lane = true;
    if (e.key === "Shift") keys.overtake = true;
    if (e.code === "Space") { keys.stop = true; e.preventDefault(); }
  });
  window.addEventListener("keyup", (e) => {
    if (e.key === "w" || e.key === "ArrowUp") keys.throttle = false;
    if (e.key === "s" || e.key === "ArrowDown") keys.brake = false;
    if (e.key === "a") keys.lane = false;
    if (e.key === "Shift") keys.overtake = false;
    if (e.code === "Space") keys.stop = false;
  });
}

function setupPedals() {
  const bind = (el, key) => {
    el.addEventListener("pointerdown", () => { pedals[key] = true; el.classList.add("pressed"); });
    el.addEventListener("pointerup", () => { pedals[key] = false; el.classList.remove("pressed"); });
    el.addEventListener("pointerleave", () => { pedals[key] = false; el.classList.remove("pressed"); });
  };
  bind($("pedal-throttle"), "throttle");
  bind($("pedal-brake"), "brake");
}

function setupOvertakeButton() {
  const btn = $("overtake-btn");
  btn.addEventListener("pointerdown", () => { overtakeHeld = true; });
  btn.addEventListener("pointerup", () => { overtakeHeld = false; });
  btn.addEventListener("pointerleave", () => { overtakeHeld = false; });
}

async function saveStrategy() {
  const addr = $("strategy-car-select").value;
  if (!addr) return;
  const pitLaps = $("strategy-pit-laps").value.split(",")
    .map((s) => parseInt(s.trim(), 10)).filter((n) => !Number.isNaN(n));
  await post(`/api/cars/${addr}/strategy`, {
    fuel_load: parseFloat($("strategy-fuel-load").value),
    compound: $("strategy-compound").value,
    planned_pit_laps: pitLaps,
  });
}

function drawStrategyGraph(data) {
  const canvas = $("strategy-graph");
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height, pad = 40;
  ctx.clearRect(0, 0, W, H);

  const maxLap = Math.max(1, ...data.planned.map((p) => p.lap));
  const xFor = (lap) => pad + (lap / maxLap) * (W - pad * 2);
  const yFor = (pct) => H - pad - (Math.max(0, Math.min(100, pct)) / 100) * (H - pad * 2);

  ctx.strokeStyle = "#2a3341";
  ctx.beginPath();
  ctx.moveTo(pad, pad); ctx.lineTo(pad, H - pad); ctx.lineTo(W - pad, H - pad);
  ctx.stroke();
  ctx.fillStyle = "#8b98a5";
  ctx.font = "11px sans-serif";
  ctx.fillText("0%", pad - 24, H - pad + 4);
  ctx.fillText("100%", pad - 30, pad + 4);
  ctx.fillText("lap " + maxLap, W - pad - 30, H - pad + 16);

  (data.weather_forecast || []).forEach((f) => {
    const x = xFor(f.lap);
    ctx.strokeStyle = "#d29922";
    ctx.setLineDash([4, 3]);
    ctx.beginPath(); ctx.moveTo(x, pad); ctx.lineTo(x, H - pad); ctx.stroke();
    ctx.setLineDash([]);
    ctx.save();
    ctx.fillStyle = "#d29922";
    ctx.translate(x + 3, pad + 10);
    ctx.rotate(Math.PI / 2);
    ctx.fillText(`${f.predicted_level} ${Math.round(f.confidence * 100)}%`, 0, 0);
    ctx.restore();
  });

  function drawLine(points, key, color) {
    if (!points.length) return;
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    points.forEach((p, i) => {
      const x = xFor(p.lap), y = yFor(p[key]);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  drawLine(data.planned, "fuel", "#58a6ff");
  drawLine(data.planned, "tyre_wear", "#d2992299");
  drawLine(data.actual, "fuel", "#2ea043");
  drawLine(data.actual, "tyre_wear", "#da3633");

  const legend = [["Planned fuel", "#58a6ff"], ["Planned tyre", "#d29922"], ["Actual fuel", "#2ea043"], ["Actual tyre", "#da3633"]];
  ctx.font = "11px sans-serif";
  legend.forEach(([label, color], i) => {
    ctx.fillStyle = color;
    ctx.fillRect(pad + i * 140, 8, 10, 10);
    ctx.fillStyle = "#e6edf3";
    ctx.fillText(label, pad + i * 140 + 14, 17);
  });
}

async function refreshStrategyGraph() {
  const addr = $("strategy-car-select").value;
  const totalLaps = parseInt($("strategy-total-laps").value, 10);
  const avgLap = parseFloat($("strategy-avg-lap").value);
  if (!addr || !totalLaps) return;
  const resp = await fetch(`/api/cars/${addr}/strategy/graph?total_laps=${totalLaps}&avg_lap_seconds=${avgLap}`);
  if (!resp.ok) return;
  drawStrategyGraph(await resp.json());
}

function setupControls() {
  $("go-btn").onclick = () => post("/api/race/countdown");
  $("go-instant-btn").onclick = () => post("/api/race/go");
  $("stop-btn").onclick = () => post("/api/race/stop", { triggered_by: null });
  $("resume-btn").onclick = () => post("/api/race/resume");
  $("reset-btn").onclick = () => post("/api/race/reset");
  $("safety-car-btn").onclick = () => post("/api/race/safety_car", { action: "trigger" });
  $("safety-car-end-btn").onclick = () => post("/api/race/safety_car", { action: "end" });

  $("mode-select").onchange = (e) => post("/api/race/mode", { mode: e.target.value });
  $("weather-select").onchange = (e) => post("/api/race/weather", { level: e.target.value });

  $("debug-toggle").onclick = () => $("debug-panel").classList.toggle("open");

  $("assign-btn").onclick = () => {
    const addr = $("my-car-select").value;
    post(`/api/cars/${addr}/assign`, {
      controller_id: $("my-controller-id").value || "player1",
      name: $("my-car-name").value,
    });
  };

  $("pit-toggle-btn").onclick = async () => {
    const addr = $("my-car-select").value;
    const car = latestState && latestState.cars[addr];
    await post(`/api/cars/${addr}/pit`, { in_pit: !(car && car.in_pit) });
  };

  $("sens-throttle-exp").oninput = (e) => $("sens-throttle-exp-val").textContent = e.target.value;
  $("sens-brake-exp").oninput = (e) => $("sens-brake-exp-val").textContent = e.target.value;
  $("sens-apply").onclick = () => {
    const addr = $("my-car-select").value;
    post(`/api/cars/${addr}/sensitivity`, {
      throttle_exponent: parseFloat($("sens-throttle-exp").value),
      brake_exponent: parseFloat($("sens-brake-exp").value),
      throttle_gain: 1.0, brake_gain: 1.0,
    });
  };

  $("rec-start").onclick = () => {
    const addr = $("my-car-select").value;
    post("/api/recording/start", { address: parseInt(addr, 10), name: $("rec-name").value });
  };
  $("rec-stop").onclick = () => {
    const addr = $("my-car-select").value;
    post(`/api/recording/stop/${addr}`);
  };

  $("ghost-set-btn").onclick = () => {
    const addr = $("my-car-select").value;
    post(`/api/cars/${addr}/ghost`, { recording_name: $("ghost-name").value });
  };
  $("ghost-clear-btn").onclick = () => {
    const addr = $("my-car-select").value;
    post(`/api/cars/${addr}/ghost/clear`);
  };

  $("strategy-fuel-load").oninput = (e) => $("strategy-fuel-load-val").textContent = e.target.value;
  $("strategy-save-btn").onclick = async () => { await saveStrategy(); refreshStrategyGraph(); };
  $("strategy-recommend-btn").onclick = async () => {
    const addr = $("strategy-car-select").value;
    const totalLaps = $("strategy-total-laps").value;
    const avgLap = $("strategy-avg-lap").value;
    const resp = await fetch(`/api/cars/${addr}/strategy/recommend?total_laps=${totalLaps}&avg_lap_seconds=${avgLap}`);
    if (!resp.ok) return;
    const data = await resp.json();
    $("strategy-fuel-load").value = data.fuel_load;
    $("strategy-fuel-load-val").textContent = data.fuel_load;
    $("strategy-compound").value = data.compound;
    $("strategy-pit-laps").value = data.planned_pit_laps.join(", ");
    await saveStrategy();
    refreshStrategyGraph();
  };

  $("forecast-generate-btn").onclick = () => post("/api/race/forecast", {
    total_laps: parseInt($("strategy-total-laps").value, 10) || 20,
    num_changes: 2,
  });
  $("forecast-clear-btn").onclick = () => post("/api/race/forecast/clear");

  $("pace-scale").oninput = (e) => $("pace-scale-val").textContent = parseFloat(e.target.value).toFixed(2) + "x";
  $("pace-refresh").onclick = refreshRecordings;
  $("pace-play").onclick = () => {
    post("/api/pace_car/play", {
      recording_name: $("pace-recording").value,
      address: parseInt($("pace-address").value, 10),
      speed_scale: parseFloat($("pace-scale").value),
      loop: $("pace-loop").checked,
    });
  };
  $("pace-stop").onclick = () => post("/api/pace_car/stop");
}

async function refreshRecordings() {
  const resp = await fetch("/api/recording/list");
  const data = await resp.json();
  const sel = $("pace-recording");
  sel.innerHTML = "";
  data.recordings.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name; opt.textContent = name;
    sel.appendChild(opt);
  });
}

function pollDebugLog() {
  setInterval(async () => {
    if (!$("debug-panel").classList.contains("open")) return;
    const resp = await fetch("/api/debug/log");
    const data = await resp.json();
    $("debug-log").textContent = data.log.join("\n");
  }, 1000);
}

buildLights($("personal-start-lights"));
setupKeyboard();
setupPedals();
setupOvertakeButton();
setupControls();
connect();
refreshRecordings();
pollDebugLog();
setInterval(sendInput, 100);
setInterval(refreshStrategyGraph, 4000);
