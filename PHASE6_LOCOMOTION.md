# Phase 6 — Locomotion

> **Real walking gait + IMU loop + cliff guard.**
> Only after Phase 5 (Radxa + Pipecat + Gemini Live) is up and the `walk()` tool exists.

---

## Goal

Make the body actually move when the agent calls `walk("forward", N)` or `turn("left", deg)`. The TARS-canonical gait uses **two arm servos** rotating around the **vertical axis** of the chassis (`SERVO_AXIS_Z=145`, `PIVOT_Z=210`), so the lower arms sweep the floor in alternation, dragging the body forward like the movie robot.

After Phase 6, TARS:

- Walks ~25 cm per "step cycle" (two servo half-strokes) on smooth floors.
- Turns in place ±15° per cycle.
- Refuses to move when the cliff sensor or IMU says no.
- Reports orientation/fall back to the agent on the UART bus.

---

## Mechanical Principle

The two lateral arms (39 × 39 × 234 mm) are mounted on horns at `Z = 145 mm` (`SERVO_AXIS_Z`). Each arm can rotate around its **vertical axis** (the servo horn points sideways, the arm hangs from it like a paddle). When the bottom of the arm pushes outward and downward against the floor, friction translates into a forward thrust on the chassis.

```
Side view (one cycle):

  step 0:  step 1:   step 2:   step 3:
  L=0°     L=+60°    L=0°      L=-60°
  R=0°     R=-60°    R=0°      R=+60°
   │        │\        │         │/
   │        │ \       │         │/
   ▼        ▼  \      ▼         ▼
  ──────  ──────────  ──────  ──────────
                 ↑ forward
```

Each half-stroke (60°) drags the chassis ~6-8 cm. A full cycle (4 phases) advances ~25 cm. The strong **Corona DS-538MG** servos (4.5 kg·cm) provide enough torque to move the ~370 g body. The previous EMAX ES08MD (2 kg·cm) **could not** sustain this load — that is why Phase 3 was upgraded.

---

## Required Hardware (delta vs Phase 3-5)

| Component | Function | Phase |
|---|---|---|
| 2× Corona DS-538MG | already added in P3 (replaces ES08MD) | 3 |
| MPU6050 (IMU 6-axis) | tilt + fall detection | 2 (added) |
| VL53L0X (downward) | anti-cliff: detects edges and stairs | 2 (added) |
| 1000 µF capacitor on servo 5V | absorbs current spikes during dual start | 3 |
| (recommended) second MT3608 | isolates servo rail from Radxa rail | 3 |
| Silicone wire 28 AWG for servos | flexible, handles 3-4 A peak | 3 |

If you skipped any of these in P2/P3, install them before Phase 6 — the gait code depends on them.

---

## Sensor Layout

```
                 ┌─── VL53L1X frontal (0-4m, FOV 27°)
                 │
   front view:   ▼
   ┌──────────────────────┐
   │  ◉             ◉     │ ← VL53L1X 45° L + R (height ~80 mm)
   │                      │
   │                      │
   │     [OLED face]      │
   │                      │
   │                      │
   │   ◉ VL53L0X cliff    │ ← downward, mounted at front-bottom edge,
   └──────────────────────┘   tilted 30° forward, sees ~120 mm ahead
        ▲
        └─ floor
```

I²C addresses (set via XSHUT at boot):

| Sensor | Default | Reassigned |
|---|---|---|
| VL53L1X frontal | 0x29 | 0x30 |
| VL53L1X left 45° | 0x29 | 0x31 |
| VL53L1X right 45° | 0x29 | 0x32 |
| VL53L0X cliff | 0x29 | 0x33 |
| MPU6050 | 0x68 | 0x68 (no conflict) |
| OLED SSD1309 | 0x3C | 0x3C |

XSHUT pins on XIAO: `D0..D3`. Boot sequence: hold all XSHUT low → bring up one by one, calling `setAddress()`.

---

## Firmware: gait state machine (XIAO)

Add `tars/gait.h` and `tars/gait.cpp` to the body daemon firmware.

### `gait.h`

```cpp
#pragma once
#include <Arduino.h>

namespace gait {

enum class State : uint8_t {
    IDLE,
    STEP_FW_PUSH_L,    // L=+60, R=-60
    STEP_FW_RECOVER,   // L=0,   R=0
    STEP_FW_PUSH_R,    // L=-60, R=+60
    STEP_BW_PUSH,
    STEP_BW_RECOVER,
    TURN_L,
    TURN_R,
    EMERGENCY_STOP
};

void setup();           // attach servos to Phase 3 pins
void loop();            // call from main loop()
void walkForward(uint8_t steps);   // queue N forward step cycles
void walkBackward(uint8_t steps);  // queue N backward
void turnLeft(uint16_t deg);
void turnRight(uint16_t deg);
void stop();
bool isBusy();

} // namespace gait
```

### `gait.cpp` (core logic)

```cpp
#include "gait.h"
#include <ESP32Servo.h>
#include "imu.h"
#include "tof.h"

namespace gait {

static Servo servoL, servoR;
static State state = State::IDLE;
static uint8_t stepsRemaining = 0;
static uint32_t phaseUntilMs = 0;

constexpr uint8_t PIN_SERVO_L = 2;
constexpr uint8_t PIN_SERVO_R = 3;
constexpr int CENTER_L = 90;
constexpr int CENTER_R = 90;
constexpr int STROKE_DEG = 60;       // ±60°
constexpr uint32_t HALF_STEP_MS = 350;
constexpr float MAX_TILT_DEG = 25.0f;
constexpr uint16_t CLIFF_SAFE_MM = 80;

static void writeServos(int leftDeg, int rightDeg) {
    // mirror the right servo (mounted opposite)
    servoL.write(constrain(CENTER_L + leftDeg,  30, 150));
    servoR.write(constrain(CENTER_R - rightDeg, 30, 150));
}

static bool safetyTrip() {
    if (imu::isFallen() || imu::tiltDeg() > MAX_TILT_DEG) return true;
    if (state == State::STEP_FW_PUSH_L || state == State::STEP_FW_PUSH_R
        || state == State::STEP_FW_RECOVER) {
        if (tof::cliffMm() > 150 || tof::frontMm() < 200) return true;
    }
    return false;
}

void setup() {
    servoL.attach(PIN_SERVO_L, 500, 2400);
    servoR.attach(PIN_SERVO_R, 500, 2400);
    writeServos(0, 0);
}

void walkForward(uint8_t steps)  { stepsRemaining = steps;
                                   state = State::STEP_FW_PUSH_L;
                                   phaseUntilMs = millis() + HALF_STEP_MS; }
void walkBackward(uint8_t steps) { stepsRemaining = min<uint8_t>(steps, 2);
                                   state = State::STEP_BW_PUSH;
                                   phaseUntilMs = millis() + HALF_STEP_MS; }
void turnLeft(uint16_t deg)      { stepsRemaining = (deg + 14) / 15;
                                   state = State::TURN_L;
                                   phaseUntilMs = millis() + HALF_STEP_MS; }
void turnRight(uint16_t deg)     { stepsRemaining = (deg + 14) / 15;
                                   state = State::TURN_R;
                                   phaseUntilMs = millis() + HALF_STEP_MS; }
void stop()                      { state = State::EMERGENCY_STOP; writeServos(0, 0); }
bool isBusy()                    { return state != State::IDLE; }

void loop() {
    if (state == State::IDLE) return;

    if (safetyTrip()) {
        state = State::EMERGENCY_STOP;
        writeServos(0, 0);
        Serial.println("EVT SAFETY_TRIP");
        return;
    }

    if (millis() < phaseUntilMs) return;

    switch (state) {
    case State::STEP_FW_PUSH_L:
        writeServos(+STROKE_DEG, -STROKE_DEG);
        state = State::STEP_FW_RECOVER;
        phaseUntilMs = millis() + HALF_STEP_MS;
        break;
    case State::STEP_FW_RECOVER:
        writeServos(0, 0);
        if (--stepsRemaining == 0) { state = State::IDLE; }
        else { state = State::STEP_FW_PUSH_R;
               phaseUntilMs = millis() + HALF_STEP_MS; }
        break;
    case State::STEP_FW_PUSH_R:
        writeServos(-STROKE_DEG, +STROKE_DEG);
        state = State::STEP_FW_RECOVER;
        phaseUntilMs = millis() + HALF_STEP_MS;
        break;
    case State::TURN_L:
        writeServos(-STROKE_DEG, -STROKE_DEG);  // both push same side
        delay(HALF_STEP_MS);
        writeServos(0, 0);
        if (--stepsRemaining == 0) state = State::IDLE;
        phaseUntilMs = millis() + HALF_STEP_MS;
        break;
    case State::TURN_R:
        writeServos(+STROKE_DEG, +STROKE_DEG);
        delay(HALF_STEP_MS);
        writeServos(0, 0);
        if (--stepsRemaining == 0) state = State::IDLE;
        phaseUntilMs = millis() + HALF_STEP_MS;
        break;
    case State::STEP_BW_PUSH:
        writeServos(-STROKE_DEG/2, +STROKE_DEG/2);
        state = State::STEP_BW_RECOVER;
        phaseUntilMs = millis() + HALF_STEP_MS;
        break;
    case State::STEP_BW_RECOVER:
        writeServos(0, 0);
        if (--stepsRemaining == 0) state = State::IDLE;
        else phaseUntilMs = millis() + HALF_STEP_MS;
        break;
    case State::EMERGENCY_STOP:
    case State::IDLE:
        break;
    }
}

} // namespace gait
```

### UART command handler (in `tars.ino`)

```cpp
void onUartCommand(const String& cmd) {
    if      (cmd.startsWith("WALK FW ")) gait::walkForward(cmd.substring(8).toInt());
    else if (cmd.startsWith("WALK BW ")) gait::walkBackward(cmd.substring(8).toInt());
    else if (cmd.startsWith("TURN L "))  gait::turnLeft(cmd.substring(7).toInt());
    else if (cmd.startsWith("TURN R "))  gait::turnRight(cmd.substring(7).toInt());
    else if (cmd == "STOP")              gait::stop();
    else if (cmd == "BUSY")              Serial.printf("BUSY %d\n", gait::isBusy());
    else if (cmd == "IMU")               imu::printAll();
    else if (cmd == "CLIFF")             Serial.printf("CLIFF %d\n", tof::cliffMm());
    else if (cmd.startsWith("TOF "))     tof::reply(cmd[4]);
    else if (cmd.startsWith("FACE "))    oled::face(cmd.substring(5));
    else if (cmd == "BAT")               Serial.printf("BAT %.2f %d\n",
                                            power::voltage(), power::percent());
}
```

---

## IMU module (`tars/imu.h/.cpp`)

```cpp
#pragma once
namespace imu {
    void setup();           // I2C MPU6050 0x68
    void poll();            // call every loop, updates pitch/roll/yaw
    float pitchDeg();
    float rollDeg();
    float yawDeg();
    float tiltDeg();        // max(|pitch|, |roll|)
    bool  isFallen();       // tilt > 60° sustained 200ms
    void  printAll();       // "IMU pitch=.. roll=.. yaw=.. fall=.."
}
```

Use the `MPU6050_light` Arduino library for compactness. Calibrate on startup (`mpu.calcOffsets()` while standing still on flat floor).

---

## ToF module (`tars/tof.h/.cpp`)

```cpp
#pragma once
namespace tof {
    void     setup();        // XSHUT init, set 0x30/0x31/0x32/0x33
    uint16_t frontMm();
    uint16_t leftMm();
    uint16_t rightMm();
    uint16_t cliffMm();      // VL53L0X downward, larger value = ground further (=cliff)
    void     reply(char dir); // dir in {'F','L','R','D'}
}
```

Cliff threshold:
- Floor at expected distance (~80-110 mm with 30° tilt) → safe.
- Reading > 150 mm → edge detected → **immediate STOP signal**.

---

## Anti-stairs Strategy (3-layer defense)

| Layer | Implementation | Where |
|---|---|---|
| 1. Hardware | VL53L0X cliff sensor on XIAO halts gait state machine before Radxa even hears about it | XIAO firmware |
| 2. Vision | Gemini Live system prompt: "veo escalones / borde / desnivel" → call `STOP` | Radxa system prompt |
| 3. Geofencing | OpenClaw skill `tars_robot` blocks `walk()` if room tag = "stairs_nearby" | OpenClaw memory |

All three layers must agree before the robot crosses a threshold. If any one says no, motion is blocked.

---

## Calibration Procedure

1. **Servo center**: with the robot held in air, run UART `CAL CENTER`. The XIAO writes `90,90` and you adjust the horns mechanically until both arms hang vertically.
2. **IMU**: place the robot on a flat surface, send `CAL IMU`. The XIAO averages 500 samples to set offsets.
3. **Cliff baseline**: place robot on floor, send `CAL CLIFF`. Stores the "floor here" reading; cliff trip = baseline + 70 mm.
4. **Step length**: send `WALK FW 4` and measure traveled distance. Record in OpenClaw memory: `remember("step_length_mm: 250 on parquet")`. The agent uses this to plan paths.

---

## Power Considerations

Two Corona DS-538MG can each draw ~1.5-2 A peak (stall ~3 A). Without isolation:

- Servo start spike pulls servo rail from 5V to ~4.2V.
- Radxa Zero 2 Pro browns out at <4.6V → kernel panic.

Mitigations applied in P3 + P5:

1. **1000 µF electrolytic** across servo +5V/GND right at the servo connector.
2. **Second MT3608** (recommended) dedicated to servos, separate from Radxa+XIAO+audio rail.
3. **Silicone 28 AWG** wires for servo power (low resistance, no fire hazard if a phase stalls).
4. Gait state machine **never runs both push phases simultaneously** — only push-recover-push.

---

## Battery Budget

| Mode | Current draw | Time on 4200 mAh |
|---|---|---|
| Idle (Radxa idle, XIAO listening) | ~400 mA | ~10 h |
| Conversation only (Gemini Live streaming) | ~700 mA | ~6 h |
| Conversation + walking | ~1.2 A average | ~3 h |
| Walking continuous | ~1.5 A | ~2.5 h |

For longer autonomy expose a USB-C charging port on the rear lid (charging while sitting).

---

## Tool Calls Wired to Gait

In `brain/tars_brain/tools.py` (Phase 5), the previously defined `walk()`, `turn()` and `check_safe_to_move()` now actually move the robot:

```python
async def walk(direction: str, steps: int) -> str:
    if not await check_safe_to_move():
        return "Detecto un desnivel, no avanzo."
    cmd = "WALK FW" if direction == "forward" else "WALK BW"
    await esp32_uart_send(f"{cmd} {min(steps, 10)}")
    while await esp32_uart_query("BUSY") == "1":
        await asyncio.sleep(0.1)
        if (await check_orientation())["fall"]:
            await esp32_uart_send("STOP")
            return "He perdido el equilibrio. He parado."
    return f"He caminado {steps} pasos {direction}."
```

---

## Verification Checklist

- [ ] `WALK FW 1` produces a single forward cycle, robot ends ~25 cm ahead.
- [ ] `WALK FW 4` produces 4 cycles, ~1 m advance, no current sag visible on multimeter.
- [ ] `TURN L 90` rotates ~90° in place (±15° tolerance).
- [ ] Placing robot on table edge → cliff sensor halts forward motion within 300 ms.
- [ ] Tipping robot >25° → IMU triggers EMERGENCY_STOP, OLED shows angry face.
- [ ] Battery sustains 30 min mixed walking + conversation without brownout.
- [ ] Agent (Phase 5) successfully invokes `walk()` from voice command and reports back.

---

## After Phase 6

The robot is **complete**. From here the work is software-only:

- Tune gait timing per surface (parquet vs carpet).
- Train OpenClaw memory with personal facts ("mi habitación es a la derecha de la cocina").
- Add custom skills (alarm clock, weather report, intruder watch).
- Optionally add a sleep schedule (`sleep_after_minutes_idle: 5`).

---

> *"I'm not really walking. I'm controlled stumbling. Same outcome."* — TARS post Phase 6
