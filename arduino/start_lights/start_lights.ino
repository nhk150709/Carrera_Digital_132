/*
 * Example: 5-light F1-style start sequence, driven by the Pi's serial
 * protocol (see app/network/arduino_api.py).
 *
 * Wiring: 5 LEDs (+ resistors) on pins 2-6. Optional physical stop button
 * on pin 7 (active LOW, INPUT_PULLUP) reporting back to the Pi as this
 * car/player's address -- change STOP_ADDRESS to match.
 *
 * Protocol lines received from the Pi, one per line, newline-terminated:
 *   START ARMED   -> all LEDs off, sequence about to begin
 *   START L1..L5  -> light up that many LEDs (L1 = first lit, L5 = all five)
 *   START GO      -> all LEDs off (the "lights out" moment = go)
 *
 * Lines sent back to the Pi:
 *   BTN STOP <address>   when the stop button is pressed
 */

const int LED_PINS[5] = {2, 3, 4, 5, 6};
const int STOP_BUTTON_PIN = 7;
const int STOP_ADDRESS = 0;  // this station reports stops for car/player 0

String lineBuffer;

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < 5; i++) {
    pinMode(LED_PINS[i], OUTPUT);
    digitalWrite(LED_PINS[i], LOW);
  }
  pinMode(STOP_BUTTON_PIN, INPUT_PULLUP);
}

void setLights(int count) {
  for (int i = 0; i < 5; i++) {
    digitalWrite(LED_PINS[i], i < count ? HIGH : LOW);
  }
}

void handleLine(const String &line) {
  if (!line.startsWith("START ")) return;
  String phase = line.substring(6);
  phase.trim();

  if (phase == "ARMED") {
    setLights(0);
  } else if (phase == "GO") {
    setLights(0);
  } else if (phase.startsWith("L") && phase.length() == 2) {
    int n = phase.charAt(1) - '0';
    if (n >= 1 && n <= 5) setLights(n);
  }
}

bool lastButtonState = HIGH;

void checkStopButton() {
  bool state = digitalRead(STOP_BUTTON_PIN);
  if (state == LOW && lastButtonState == HIGH) {
    Serial.print("BTN STOP ");
    Serial.println(STOP_ADDRESS);
  }
  lastButtonState = state;
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n') {
      handleLine(lineBuffer);
      lineBuffer = "";
    } else if (c != '\r') {
      lineBuffer += c;
    }
  }
  checkStopButton();
}
