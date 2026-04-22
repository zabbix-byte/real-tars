# TARS · Phase 1 - Arduino IDE version

Sketch de Arduino IDE para **XIAO ESP32-S3 Sense**.

> Si prefieres PlatformIO (mejor para proyectos grandes), usa la carpeta [`../phase1_firmware`](../phase1_firmware).

---

## 1. Preparar Arduino IDE (una sola vez)

### a) Instalar soporte ESP32
1. Abre Arduino IDE.
2. `File → Preferences → Additional Board Manager URLs`, pega:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
3. `Tools → Board → Boards Manager` → busca **esp32** → instala **"esp32 by Espressif Systems"** (versión ≥ 3.0.0).

### b) Instalar librería
1. `Sketch → Include Library → Manage Libraries`.
2. Busca **ArduinoJson** (by Benoit Blanchon) → Install.

### c) Seleccionar la placa
`Tools → Board → ESP32 Arduino → XIAO_ESP32S3`

Y en el menú `Tools` ajusta:

| Opción | Valor |
|---|---|
| **USB CDC On Boot** | `Enabled` |
| **USB Mode** | `Hardware CDC and JTAG` |
| **PSRAM** | `OPI PSRAM` |
| **Flash Size** | `8MB` |
| **Partition Scheme** | `Huge APP (3MB No OTA/1MB SPIFFS)` |
| **Upload Speed** | `921600` |

---

## 2. Configurar el sketch

1. Copia `config.h.example` → `config.h` (en la misma carpeta).
2. Abre `config.h` y pon tus claves reales:
   - WiFi SSID + password (¡2.4 GHz!).
   - `GROQ_API_KEY` desde https://console.groq.com
   - `WHATSAPP_PHONE` y `CALLMEBOT_KEY` (ver README principal para activar CallMeBot).

---

## 3. Flashear

1. Conecta el XIAO por USB-C.
2. `Tools → Port` → selecciona el COM del XIAO.
3. Abre `tars_phase1.ino` (Arduino IDE cargará también los `.h` y `.cpp` automáticamente, los verás como pestañas arriba).
4. Pulsa **Upload** (→).
5. Abre **Serial Monitor** a `115200` baud.

> Si falla el upload: mantén pulsado **BOOT** mientras enchufas el USB, luego suelta y vuelve a darle Upload.

---

## 4. Uso

Habla cerca del XIAO. Cuando dejes de hablar ~1 s, TARS procesa y te manda la respuesta sarcástica por WhatsApp.

Salida típica del monitor serie:

```
===============================================
   TARS - Phase 1 Brain
===============================================
  Humor level: 75%
  STT model  : whisper-large-v3-turbo
  LLM model  : llama-3.1-8b-instant
===============================================
Connecting to WiFi: mi_red
......
WiFi OK, IP=192.168.1.42, RSSI=-58
Audio ready: 80000 samples, 160000 bytes PSRAM
TARS online. Speak to me. Or don't. I'm a robot.
Listening for wake sound...
Voice detected (amp=2840)
Recording...
Recorded 42300 samples (84644 bytes WAV)
[STT] -> Hola TARS, que tal estas?
[USER ] Hola TARS, que tal estas?
[LLM] -> Funcional. Lo cual es mas de lo que puedo decir de ti.
[TARS ] Funcional. Lo cual es mas de lo que puedo decir de ti.
[WA] WhatsApp sent OK
---------- ready for next input ----------
```

---

## 5. Archivos de este sketch

```
tars_phase1/
├── tars_phase1.ino         ← abrelo con Arduino IDE
├── config.h.example        ← copia a config.h
├── wifi_manager.{h,cpp}
├── audio_recorder.{h,cpp}  ← PDM I2S (GPIO 41/42)
├── groq_client.{h,cpp}     ← Whisper + Llama
└── whatsapp_client.{h,cpp} ← CallMeBot
```

Arduino IDE muestra todos estos archivos como **pestañas** en la parte superior del editor.

---

## 6. Problemas comunes

| Síntoma | Solución |
|---|---|
| `fatal error: ESP_I2S.h: No such file` | Actualiza el core ESP32 a ≥ 3.0.0 (`ESP_I2S.h` solo existe en 3.x). |
| `PSRAM not detected` | `Tools → PSRAM: OPI PSRAM` |
| Sketch demasiado grande | `Tools → Partition Scheme: Huge APP` |
| No detecta el COM | Pulsa BOOT + RESET, o instala el driver CP210x |
| WiFi no conecta | Comprueba que es **2.4 GHz** (ESP32 no soporta 5 GHz) |
