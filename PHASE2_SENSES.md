# Phase 2 — The Senses

> **LiDAR + Speaker + DAC**
> El robot te "oye" y "habla" fisicamente.

---

## Overview

Phase 2 gives TARS **physical senses**. After Phase 1, TARS could think and respond via WhatsApp — now it gains a **real voice** through a speaker and **spatial awareness** through two VL53L1X ToF laser sensors. TARS stops being a silent brain and becomes a robot that talks out loud and perceives the world around it.

**End result:** You speak → TARS listens through the microphone → thinks via Groq → responds OUT LOUD through the speaker + sends distance/proximity alerts.

---

## What Changes from Phase 1

```mermaid
graph LR
    subgraph PHASE1["Phase 1 - Brain Only"]
        P1_IN["Microphone + Camera"]
        P1_BRAIN["Groq AI"]
        P1_OUT["WhatsApp text"]
    end

    subgraph PHASE2["Phase 2 - Physical Senses"]
        P2_IN["Microphone + Camera + LiDAR"]
        P2_BRAIN["Groq AI"]
        P2_OUT["Speaker audio + WhatsApp"]
    end

    P1_IN --> P1_BRAIN --> P1_OUT
    P2_IN --> P2_BRAIN --> P2_OUT
```

| Capability | Phase 1 | Phase 2 |
|------------|---------|---------|
| Hears you | Via PDM microphone | Same microphone |
| Thinks | Groq Llama 3.1 | Same Groq |
| Responds | WhatsApp text only | **Physical speaker + WhatsApp** |
| Sees | Camera to Groq Vision | Same camera |
| Senses distance | No | **2x VL53L1X ToF (front + 45deg, 0-4m)** |
| Detects approach | No | **Triggers greeting when someone nears** |

---

## Architecture

```mermaid
graph TB
    subgraph HARDWARE["HARDWARE LAYER"]
        MIC["PDM Microphone"]
        CAM["OV2640 Camera"]
        LIDAR["2x VL53L1X ToF (front + 45 deg)"]
        AMP["MAX98357A I2S DAC Amplifier"]
        SPK["3W 8 Ohm 40mm Speaker"]
    end

    subgraph XIAO["XIAO ESP32-S3 Sense"]
        OC["OpenClaw Firmware"]
        I2C["I2C Bus"]
        I2S["I2S Audio Bus"]
    end

    subgraph CLOUD["INTELLIGENCE - Groq + OpenAI"]
        STT["Whisper STT"]
        LLM["Llama 3.1 8B"]
        VIS["Llama 4 Scout"]
        TTS["OpenAI tts-1 Onyx"]
    end

    MIC --> OC
    CAM --> OC
    LIDAR -->|"I2C"| I2C
    I2C --> OC
    OC -->|"WiFi"| STT
    OC -->|"WiFi"| VIS
    STT --> LLM
    VIS --> LLM
    LLM --> TTS
    TTS -->|"Audio data"| OC
    OC -->|"I2S"| AMP
    AMP --> SPK
```

---

## New Components (Phase 2)

| # | Component | Price | Function |
|---|-----------|-------|----------|
| 1 | 2x VL53L1X Laser Range Sensor | €23.98 | Distance + obstacle detection (front + 45deg) |
| 2 | MAX98357A I2S DAC Amplifier 3W | €9.99 | Digital audio to amplified speaker signal |
| 3 | Speaker 3W 8 Ohm 40mm diameter | €8.99 | TARS physical voice output |
| | **Phase 2 additions** | **€42.96** | |
| | **Cumulative total (Phase 1 + 2)** | **€106.84** | |

> **Note:** Phase 2 still uses USB power from Phase 1. Battery comes in Phase 3.

---

## VL53L1X — Distance Sensor (ToF) × 2

### What Is It?

A **Time of Flight (ToF)** laser sensor that measures distance with millimetric precision by timing how long a laser pulse takes to bounce back. We use **two** of them: one facing **front** and one facing **45°** diagonally, so TARS has a simple stereo-ish spatial awareness.

### Specifications (VL53L1X)

| Spec | Value |
|------|-------|
| Range | Up to ~4 meters |
| Interface | I²C |
| Accuracy | +/- 3% |
| Speed | Up to 50Hz |
| Default I²C address | 0x29 (reassigned at boot to 0x30 / 0x31 via XSHUT) |
| Voltage | 2.6V - 5.5V |

### What Does It Do in TARS?

- **Obstacle detection:** TARS knows if something is in front of it
- **Proximity greeting:** Detects when someone approaches and triggers a sarcastic greeting
- **Environment awareness:** Sends distance data to Groq for contextual responses
- **Safety:** Prevents TARS from walking into walls (Phase 3+)
- **Stereo-ish:** Two sensors (front + 45°) disambiguate where the target is

### Wiring to ESP32-S3

```mermaid
graph LR
    subgraph VL53["VL53L1X Sensor (x2)"]
        V_VCC["VCC"]
        V_GND["GND"]
        V_SDA["SDA"]
        V_SCL["SCL"]
    end

    subgraph ESP32["XIAO ESP32-S3"]
        E_3V["3.3V"]
        E_GND["GND"]
        E_SDA["GPIO5 SDA"]
        E_SCL["GPIO6 SCL"]
    end

    V_VCC --- E_3V
    V_GND --- E_GND
    V_SDA --- E_SDA
    V_SCL --- E_SCL
```

| VL53L1X Pin | ESP32-S3 Pin | Wire Color (suggested) |
|-------------|-------------|----------------------|
| VCC | 3.3V | Red |
| GND | GND | Black |
| SDA | GPIO5 | Blue |
| SCL | GPIO6 | Yellow |

### Arduino Code — Distance Reading (2x VL53L1X)

```cpp
#include <Wire.h>
#include <VL53L1X.h>

VL53L1X sensor1;   // front
VL53L1X sensor2;   // 45 deg diagonal

#define XSHUT1 2
#define XSHUT2 3

void setup() {
    Serial.begin(115200);
    pinMode(XSHUT1, OUTPUT);
    pinMode(XSHUT2, OUTPUT);
    digitalWrite(XSHUT1, LOW);
    digitalWrite(XSHUT2, LOW);
    delay(10);

    Wire.begin(5, 6);  // SDA=GPIO5, SCL=GPIO6 (shared bus)

    // Boot sensor 1 first, reassign to 0x30
    digitalWrite(XSHUT1, HIGH); delay(10);
    sensor1.init();
    sensor1.setAddress(0x30);

    // Then sensor 2, reassign to 0x31
    digitalWrite(XSHUT2, HIGH); delay(10);
    sensor2.init();
    sensor2.setAddress(0x31);

    sensor1.startContinuous(50);
    sensor2.startContinuous(50);
}

void loop() {
    int d_front = sensor1.read();
    int d_side  = sensor2.read();

    if (d_front < 500) triggerGreeting(d_front);

    Serial.printf("front=%d mm  45deg=%d mm\n", d_front, d_side);
    delay(100);
}

void triggerGreeting(int distance) {
    String payload = "{\"event\":\"proximity\",\"distance_mm\":" + String(distance) + "}";
    sendToOpenClaw(payload);
}
```

---

## MAX98357A — I2S DAC Amplifier

### What Is It?

A **Class D digital audio amplifier** that takes I2S digital audio directly from the ESP32 and outputs amplified analog signal to a speaker. No separate DAC needed — it's all in one chip.

### Specifications

| Spec | Value |
|------|-------|
| Output Power | 3.2W at 4 Ohm, 1.8W at 8 Ohm |
| Input | I2S digital audio |
| Voltage | 2.5V - 5.5V |
| THD+N | 0.015% at 1kHz |
| Sample Rate | Up to 96kHz |
| No external components needed | Built-in clock recovery |

### Wiring to ESP32-S3

```mermaid
graph LR
    subgraph AMP["MAX98357A Amplifier"]
        A_VIN["VIN"]
        A_GND["GND"]
        A_BCLK["BCLK"]
        A_LRC["LRC - Word Select"]
        A_DIN["DIN - Data"]
        A_OUTP["OUT+"]
        A_OUTN["OUT-"]
    end

    subgraph ESP32["XIAO ESP32-S3"]
        E_5V["5V USB"]
        E_GND["GND"]
        E_G1["GPIO1"]
        E_G2["GPIO2"]
        E_G3["GPIO3"]
    end

    SPK["Speaker 3W 8 Ohm"]

    A_VIN --- E_5V
    A_GND --- E_GND
    A_BCLK --- E_G1
    A_LRC --- E_G2
    A_DIN --- E_G3
    A_OUTP --- SPK
    A_OUTN --- SPK
```

| MAX98357A Pin | ESP32-S3 Pin | Function |
|-------------|-------------|----------|
| VIN | 5V (USB in Phase 2, MT3608 in Phase 3) | Power |
| GND | GND | Ground |
| BCLK | GPIO7 | I2S Bit Clock |
| LRC | GPIO8 | I2S Word Select (Left/Right Clock) |
| DIN | GPIO9 | I2S Data Input |
| OUT+ | Speaker + | Amplified audio positive |
| OUT- | Speaker - | Amplified audio negative |

> **Why GPIO 7/8/9 instead of 1/2/3?** GPIO 1 is reserved for the battery ADC monitor (Phase 3), and GPIO 2/3 are reserved for the VL53L1X XSHUT lines. 7/8/9 are contiguous and free on the XIAO ESP32-S3 Sense.

> **Phase 2 Note:** Power comes from USB 5V. In Phase 3, the DC-DC Step-Up will provide 5V from battery.

### Arduino Code — Play Audio

```cpp
#include <driver/i2s.h>

#define I2S_BCLK  7
#define I2S_LRC   8
#define I2S_DOUT  9

void setupI2S() {
    i2s_config_t config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
        .sample_rate = 16000,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 8,
        .dma_buf_len = 1024,
        .use_apll = false
    };

    i2s_pin_config_t pins = {
        .bck_io_num = I2S_BCLK,
        .ws_io_num = I2S_LRC,
        .data_out_num = I2S_DOUT,
        .data_in_num = I2S_PIN_NO_CHANGE
    };

    i2s_driver_install(I2S_NUM_0, &config, 0, NULL);
    i2s_set_pin(I2S_NUM_0, &pins);
}

void playAudioBuffer(uint8_t* buffer, size_t length) {
    size_t bytes_written;
    i2s_write(I2S_NUM_0, buffer, length, &bytes_written, portMAX_DELAY);
}
```

---

## Speaker — 3W 8 Ohm 40mm

### Placement in TARS

TARS is a rectangular monolith. The speaker mounts **inside the central block** (see [PHASE3_MECHANICS.md](PHASE3_MECHANICS.md)) with an integrated ~25 cm³ acoustic box. In Phase 2 it sits exposed on the breadboard.

| Spec | Value |
|------|-------|
| Power | 3W |
| Impedance | 8 Ohm |
| Diameter | 40 mm |
| Quantity | 1 (single mono speaker, acoustic box integrated in chassis) |

> **Phase 2:** One speaker connected to the MAX98357A. The final chassis provides the sealed acoustic volume.

---

## Complete Phase 2 Wiring

```mermaid
graph TB
    subgraph ESP["XIAO ESP32-S3 Sense"]
        CAM["Camera OV2640"]
        MIC["Microphone PDM"]
        SDA["GPIO5 SDA"]
        SCL["GPIO6 SCL"]
        XS1["GPIO2 XSHUT #1"]
        XS2["GPIO3 XSHUT #2"]
        BCLK["GPIO7 BCLK"]
        LRC["GPIO8 LRC"]
        DIN["GPIO9 DIN"]
        USB["USB-C 5V Power"]
    end

    VL1["VL53L1X #1 (front)"]
    VL2["VL53L1X #2 (45 deg)"]
    AMP["MAX98357A Amplifier"]
    SPK["Speaker 3W 8 Ohm 40mm"]

    SDA -->|"I2C"| VL1
    SCL -->|"I2C"| VL1
    SDA -->|"I2C"| VL2
    SCL -->|"I2C"| VL2
    XS1 --> VL1
    XS2 --> VL2
    BCLK -->|"I2S"| AMP
    LRC -->|"I2S"| AMP
    DIN -->|"I2S"| AMP
    AMP --> SPK
    USB -->|"5V"| AMP
```

---

## Updated Interaction Flow (Phase 2)

```mermaid
sequenceDiagram
    actor User
    participant LIDAR as VL53L1X
    participant XIAO as XIAO ESP32-S3
    participant GROQ as Groq Cloud
    participant TTS as OpenAI TTS
    participant SPK as Speaker

    Note over LIDAR: User approaches
    LIDAR->>XIAO: Distance 40cm detected
    XIAO->>GROQ: Proximity event + audio capture
    GROQ->>GROQ: Whisper STT + Llama 3.1
    GROQ-->>XIAO: Sarcastic response text
    XIAO->>TTS: Text for Onyx voice
    TTS-->>XIAO: Audio data
    XIAO->>SPK: I2S audio playback
    Note over SPK: TARS speaks out loud!
    XIAO->>XIAO: Also sends via WhatsApp
```

---

## Step-by-Step Build Guide

### Step 1: Test VL53L1X (x2) Independently

1. Wire both VL53L1X sensors to XIAO (shared I2C: SDA=GPIO5, SCL=GPIO6) plus XSHUT on GPIO2 and GPIO3
2. Upload the dual-sensor sketch that reassigns addresses to 0x30 and 0x31
3. Open Serial Monitor at 115200 baud
4. Move your hand in front of each sensor
5. Verify readings: 0-4000mm, both sensors reporting independently

### Step 2: Test MAX98357A + Speaker Independently

1. Wire MAX98357A to XIAO (I2S: BCLK=GPIO7, LRC=GPIO8, DIN=GPIO9)
2. Power MAX98357A from USB 5V
3. Solder speaker wires to MAX98357A OUT+/OUT-
4. Upload a tone generation sketch
5. Verify you hear a test tone from the speaker

### Step 3: Test Audio Playback from OpenAI TTS

1. Generate a test audio file via OpenAI TTS API:
   ```bash
   curl https://api.openai.com/v1/audio/speech \
     -H "Authorization: Bearer sk-YOUR_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"tts-1","input":"I am TARS. Humor setting 75 percent.","voice":"onyx"}' \
     --output tars_test.mp3
   ```
2. Convert to WAV format compatible with ESP32:
   ```bash
   ffmpeg -i tars_test.mp3 -ar 16000 -ac 1 -f wav tars_test.wav
   ```
3. Stream audio data through I2S to speaker
4. Verify TARS's voice comes through clearly

### Step 4: Integrate Everything

1. Connect VL53L1X x2 AND MAX98357A+Speaker simultaneously
2. Verify I2C (sensor) and I2S (audio) don't conflict
3. Test: approach sensor → triggers Groq → response plays on speaker
4. Flash updated OpenClaw firmware with audio output enabled

### Step 5: Update config.json

Add audio output configuration:

```json
{
  "audio_output": {
    "enabled": true,
    "i2s_bclk": 1,
    "i2s_lrc": 2,
    "i2s_dout": 3,
    "sample_rate": 16000,
    "volume": 80
  },
  "lidar": {
    "enabled": true,
    "i2c_sda": 5,
    "i2c_scl": 6,
    "proximity_threshold_mm": 500,
    "trigger_greeting": true
  }
}
```

---

## Phase 2 Checklist

### Hardware
- [ ] 2x VL53L1X sensors purchased and received
- [ ] MAX98357A amplifier purchased and received
- [ ] Speaker (3W 8 Ohm 40mm) purchased and received
- [ ] VL53L1X x2 wired to I2C (GPIO5 SDA, GPIO6 SCL) + XSHUT (GPIO2, GPIO3)
- [ ] MAX98357A wired to I2S (GPIO7 BCLK, GPIO8 LRC, GPIO9 DIN)
- [ ] Speaker soldered to MAX98357A output
- [ ] All components on breadboard

### Software
- [ ] VL53L1X library installed (Pololu VL53L1X)
- [ ] Dual-sensor address reassignment (0x30, 0x31) working
- [ ] I2S audio driver configured
- [ ] Distance readings verified in Serial Monitor
- [ ] Test tone plays through speaker
- [ ] OpenAI TTS audio plays through speaker

### Integration
- [ ] Proximity detection triggers Groq response
- [ ] Groq response plays as audio through speaker
- [ ] WhatsApp still works alongside speaker
- [ ] Camera vision still functional
- [ ] No I2C/I2S bus conflicts

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| VL53L1X reads 65535 | Sensor not detected. Check I2C wiring and XSHUT sequence. Run I2C scanner sketch. |
| No sound from speaker | Check MAX98357A VIN is 5V. Verify I2S pin assignments (GPIO 7/8/9). Check speaker polarity. |
| Crackling audio | Add 100uF capacitor across MAX98357A VIN and GND. Check solder joints. |
| I2C bus hangs | Add 4.7K pull-up resistors on SDA and SCL lines. |
| Both ToF respond to same address | XSHUT reassignment failed. Ensure GPIO2/GPIO3 wired and sequence correct (sensor #2 held LOW while reassigning #1). |
| Audio too quiet | Increase volume in config.json. Use 4 Ohm speaker for more power (3.2W vs 1.8W). |

---

## I2C Address Map

| Device | I2C Address | Bus |
|--------|-------------|-----|
| VL53L1X #1 (front) | 0x30 (reassigned from 0x29 via XSHUT) | I2C (GPIO5/GPIO6) |
| VL53L1X #2 (45 deg) | 0x31 (reassigned from 0x29 via XSHUT) | I2C (GPIO5/GPIO6) |
| OLED Display (Phase 3) | 0x3C (fixed, SSD1309) | I2C (same bus, no conflict) |

> All three devices share the same I2C bus without conflict after the XSHUT boot sequence.

---

## What Phase 2 Adds vs Phase 1

| New Capability | Description |
|---------------|-------------|
| Physical voice | TARS speaks through a real speaker |
| Distance sensing | Laser measurement 0-4 meters |
| Proximity detection | Automatic greeting when approached |
| Richer sensor data | Distance data sent to Groq for context |
| Audio + text output | Speaker AND WhatsApp simultaneously |

---

## What Phase 2 Still Cannot Do

| Limitation | Solved in |
|------------|-----------|
| No movement | Phase 3 |
| No portable power (USB only) | Phase 3 |
| No OLED display yet (wiring ready) | Phase 3 |
| No physical body | Phase 3b (MECHANICS) / Phase 4 |
| Wires exposed on breadboard | Phase 3b (MECHANICS) / Phase 4 |

---

## Cost Summary

| Category | Cost |
|----------|------|
| **Phase 2 hardware** | **€42.96** |
| 2x VL53L1X Sensor | €23.98 |
| MAX98357A Amplifier | €9.99 |
| Speaker 3W 8 Ohm 40mm | €8.99 |
| **Cumulative hardware (P1+P2)** | **€106.84** |
| **Monthly services (unchanged)** | **~€2-4** |

---

> *"Everybody good? Plenty of slaves for my robot colony?"* — TARS
