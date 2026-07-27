const ADDRESSES = [0, 1, 2, 3, 4, 5, 6, 7];

let ws = null;
let latestState = null;
let keys = { throttle: false, brake: false, lane: false, stop: false };
let pedals = { throttle: false, brake: false };

function $(id) { return document.getElementById(id); }

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

function render(state) {
  $("state-badge").textContent = state.state;

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
  const carSelect = $("my-car-select");
  const carSelectHadFocus = document.activeElement === carSelect;
  const prevSelected = carSelect.value;
  carSelect.innerHTML = "";

  ADDRESSES.forEach((addr) => {
    const car = state.cars[String(addr)];
    if (!car) return;

    const opt = document.createElement("option");
    opt.value = addr;
    opt.textContent = `${addr} - ${car.name || "(unnamed)"}${addr === 6 ? " [autonomous]" : addr === 7 ? " [pace car]" : ""}`;
    carSelect.appendChild(opt);

    const card = document.createElement("div");
    card.className = "car-card";
    card.innerHTML = `
      <h3>${car.name || "Car " + addr} <span class="addr">#${addr}</span></h3>
      <div>Controller: ${car.controller_id || "-"} ${car.jump_start ? '<span class="jump">JUMP START</span>' : ""}</div>
      <div>Lap ${car.lap_count} - Best ${fmt(car.best_lap)}s - Penalty ${car.penalty_seconds}s</div>
      <div>Fuel ${Math.round(car.fuel)}%</div>
      <div class="bar fuel"><div style="width:${car.fuel}%"></div></div>
      <div>Tyre wear ${Math.round(car.tyre_wear)}%</div>
      <div class="bar tyre"><div style="width:${car.tyre_wear}%"></div></div>
      <div>${car.in_pit ? "IN PIT" : ""} ${car.recording ? "REC" : ""}</div>
    `;
    grid.appendChild(card);
  });
  if (prevSelected) carSelect.value = prevSelected;

  const pacePlaying = state.pace_car && state.pace_car.active;
  $("pace-play").disabled = pacePlaying;
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
  }));
}

function setupKeyboard() {
  window.addEventListener("keydown", (e) => {
    if (e.repeat) return;
    if (e.key === "w" || e.key === "ArrowUp") keys.throttle = true;
    if (e.key === "s" || e.key === "ArrowDown") keys.brake = true;
    if (e.key === "a") keys.lane = true;
    if (e.code === "Space") { keys.stop = true; e.preventDefault(); }
  });
  window.addEventListener("keyup", (e) => {
    if (e.key === "w" || e.key === "ArrowUp") keys.throttle = false;
    if (e.key === "s" || e.key === "ArrowDown") keys.brake = false;
    if (e.key === "a") keys.lane = false;
    if (e.code === "Space") keys.stop = false;
  });
}

function setupPedals() {
  const bind = (el, key) => {
    el.addEventListener("pointerdown", () => { pedals[key] = true; });
    el.addEventListener("pointerup", () => { pedals[key] = false; });
    el.addEventListener("pointerleave", () => { pedals[key] = false; });
  };
  bind($("pedal-throttle"), "throttle");
  bind($("pedal-brake"), "brake");
}

function setupControls() {
  $("go-btn").onclick = () => post("/api/race/countdown");
  $("stop-btn").onclick = () => post("/api/race/stop", { triggered_by: null });
  $("resume-btn").onclick = () => post("/api/race/resume");
  $("reset-btn").onclick = () => post("/api/race/reset");

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
    post("/api/recording/start", { address: parseInt(addr), name: $("rec-name").value });
  };
  $("rec-stop").onclick = () => {
    const addr = $("my-car-select").value;
    post(`/api/recording/stop/${addr}`);
  };

  $("pace-scale").oninput = (e) => $("pace-scale-val").textContent = parseFloat(e.target.value).toFixed(2) + "x";
  $("pace-refresh").onclick = refreshRecordings;
  $("pace-play").onclick = () => {
    post("/api/pace_car/play", {
      recording_name: $("pace-recording").value,
      address: parseInt($("pace-address").value),
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

setupKeyboard();
setupPedals();
setupControls();
connect();
refreshRecordings();
pollDebugLog();
setInterval(sendInput, 100);
