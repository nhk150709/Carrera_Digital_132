// Sound + voice announcer.
//
// Uses the browser's built-in Web Speech API (window.speechSynthesis) for
// text-to-speech -- free, offline, zero API keys, works in every modern
// browser, no setup required. Voice quality is robotic compared to a
// paid/cloud AI voice, but it's genuinely "solid and readily available."
//
// Also plays short sound-effect files if present under /static/sounds/ --
// none are bundled (can't ship copyrighted/third-party audio here), drop
// your own short clips in with these exact names and they'll be picked
// up automatically. Missing files fail silently (playback is wrapped in
// a no-op catch), so this works fine with zero files too, TTS-only.

const SOUND_FILES = {
  tyre_change: "/static/sounds/tyre_change.mp3",
  repair_complete: "/static/sounds/repair_complete.mp3",
  breakdown: "/static/sounds/breakdown.mp3",
  final_lap: "/static/sounds/final_lap.mp3",
  race_won: "/static/sounds/race_won.mp3",
  overtake_activated: "/static/sounds/overtake.mp3",
  jump_start: "/static/sounds/jump_start.mp3",
  weather_change: "/static/sounds/weather_change.mp3",
};

const TTS_TEXT = {
  final_lap: () => "Final lap!",
  race_won: (e) => `${e.name || "Car " + e.address} wins the race!`,
  breakdown: (e) => `Car ${e.address} has broken down`,
  repair_complete: (e) => `Car ${e.address} repair complete`,
  tyre_change: (e) => `Tyres changed on car ${e.address}`,
  overtake_activated: (e) => `Push to pass, car ${e.address}`,
  jump_start: (e) => `Jump start, car ${e.address}`,
  weather_change: (e) => `Weather changing to ${e.level}`,
};

function soundEnabled() {
  const el = document.getElementById("sound-enable");
  return !el || el.checked;
}

function playClip(type) {
  const src = SOUND_FILES[type];
  if (!src) return;
  const audio = new Audio(src);
  audio.play().catch(() => {});
}

function speak(type, payload) {
  if (!("speechSynthesis" in window)) return;
  const textFn = TTS_TEXT[type];
  if (!textFn) return;
  const utterance = new SpeechSynthesisUtterance(textFn(payload || {}));
  utterance.rate = 1.05;
  window.speechSynthesis.speak(utterance);
}

function playEvent(type, payload) {
  if (!soundEnabled()) return;
  playClip(type);
  speak(type, payload);
}

function handleEvents(events) {
  (events || []).forEach((e) => playEvent(e.type, e));
}

window.CarreraSound = { handleEvents, playEvent, speak };
