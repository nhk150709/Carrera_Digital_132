/*
 * Example: fuel/pit LED panel driven by the Pi's serial protocol (see
 * app/network/arduino_api.py). Shows each car's fuel level on its own LED
 * bar (using an 8-LED bar per car would need a shift register / PWM
 * driver for a real 6-car panel -- this example drives ONE car's
 * indicator directly on a PWM pin to keep the sketch readable, and a
 * single "active pit" LED that lights up while that car is refueling).
 *
 * Wiring:
 *   FUEL_LED_PINS[i]  -> PWM-capable pin driving car i's fuel gauge LED
 *                        brightness (or swap for a servo/7-seg driver)
 *   PIT_LED_PIN       -> lights up while WATCHED_ADDRESS is in the pit
 *
 * Protocol lines received from the Pi:
 *   STATE <idle|countdown|running|paused|finished>
 *   FUEL <addr>:<pct>,<addr>:<pct>,...
 *   PIT <addr>:<0|1>,...
 *   RANK <addr>:<name>:<pos>,...
 *   JUMP <addr>
 */

const int NUM_CARS = 6;
const int FUEL_LED_PINS[NUM_CARS] = {3, 5, 6, 9, 10, 11};  // PWM-capable pins
const int PIT_LED_PIN = 12;
const int WATCHED_ADDRESS = 0;  // which car's pit status lights PIT_LED_PIN

String lineBuffer;

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < NUM_CARS; i++) pinMode(FUEL_LED_PINS[i], OUTPUT);
  pinMode(PIT_LED_PIN, OUTPUT);
}

void handleFuelLine(const String &data) {
  // data looks like "0:87,1:42,2:100,..."
  int start = 0;
  while (start < (int)data.length()) {
    int comma = data.indexOf(',', start);
    String pair = (comma == -1) ? data.substring(start) : data.substring(start, comma);
    int colon = pair.indexOf(':');
    if (colon > 0) {
      int addr = pair.substring(0, colon).toInt();
      int pct = pair.substring(colon + 1).toInt();
      if (addr >= 0 && addr < NUM_CARS) {
        int pwm = map(constrain(pct, 0, 100), 0, 100, 0, 255);
        analogWrite(FUEL_LED_PINS[addr], pwm);
      }
    }
    if (comma == -1) break;
    start = comma + 1;
  }
}

void handlePitLine(const String &data) {
  int start = 0;
  while (start < (int)data.length()) {
    int comma = data.indexOf(',', start);
    String pair = (comma == -1) ? data.substring(start) : data.substring(start, comma);
    int colon = pair.indexOf(':');
    if (colon > 0) {
      int addr = pair.substring(0, colon).toInt();
      int val = pair.substring(colon + 1).toInt();
      if (addr == WATCHED_ADDRESS) {
        digitalWrite(PIT_LED_PIN, val ? HIGH : LOW);
      }
    }
    if (comma == -1) break;
    start = comma + 1;
  }
}

void handleLine(const String &line) {
  if (line.startsWith("FUEL ")) {
    handleFuelLine(line.substring(5));
  } else if (line.startsWith("PIT ")) {
    handlePitLine(line.substring(4));
  }
  // STATE / RANK / JUMP lines are ignored by this example sketch, but
  // follow the same "PREFIX rest-of-line" shape and are easy to add.
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
}
