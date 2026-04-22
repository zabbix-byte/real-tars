#include "vision_client.h"
#include "config.h"

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <esp_camera.h>
#include <mbedtls/base64.h>

namespace vision {

// XIAO ESP32-S3 Sense camera pinout (OV2640).
#define PWDN_GPIO_NUM    -1
#define RESET_GPIO_NUM   -1
#define XCLK_GPIO_NUM    10
#define SIOD_GPIO_NUM    40
#define SIOC_GPIO_NUM    39
#define Y9_GPIO_NUM      48
#define Y8_GPIO_NUM      11
#define Y7_GPIO_NUM      12
#define Y6_GPIO_NUM      14
#define Y5_GPIO_NUM      16
#define Y4_GPIO_NUM      18
#define Y3_GPIO_NUM      17
#define Y2_GPIO_NUM      15
#define VSYNC_GPIO_NUM   38
#define HREF_GPIO_NUM    47
#define PCLK_GPIO_NUM    13

static bool s_ready = false;

bool begin() {
#if !VISION_ENABLED
    return false;
#endif
    camera_config_t cfg = {};
    cfg.ledc_channel = LEDC_CHANNEL_0;
    cfg.ledc_timer   = LEDC_TIMER_0;
    cfg.pin_d0 = Y2_GPIO_NUM;
    cfg.pin_d1 = Y3_GPIO_NUM;
    cfg.pin_d2 = Y4_GPIO_NUM;
    cfg.pin_d3 = Y5_GPIO_NUM;
    cfg.pin_d4 = Y6_GPIO_NUM;
    cfg.pin_d5 = Y7_GPIO_NUM;
    cfg.pin_d6 = Y8_GPIO_NUM;
    cfg.pin_d7 = Y9_GPIO_NUM;
    cfg.pin_xclk    = XCLK_GPIO_NUM;
    cfg.pin_pclk    = PCLK_GPIO_NUM;
    cfg.pin_vsync   = VSYNC_GPIO_NUM;
    cfg.pin_href    = HREF_GPIO_NUM;
    cfg.pin_sccb_sda = SIOD_GPIO_NUM;
    cfg.pin_sccb_scl = SIOC_GPIO_NUM;
    cfg.pin_pwdn    = PWDN_GPIO_NUM;
    cfg.pin_reset   = RESET_GPIO_NUM;
    cfg.xclk_freq_hz = 20000000;
    cfg.frame_size   = FRAMESIZE_VGA;     // 640x480: mas rapido de subir, Scout lo digiere bien
    cfg.pixel_format = PIXFORMAT_JPEG;
    cfg.grab_mode    = CAMERA_GRAB_LATEST;
    cfg.fb_location  = CAMERA_FB_IN_PSRAM;
    cfg.jpeg_quality = 12;                // 10->12: JPEG mas pequeno, aun legible
    cfg.fb_count     = 1;

    esp_err_t err = esp_camera_init(&cfg);
    if (err != ESP_OK) {
        Serial.printf("[CAM] init failed 0x%x\n", err);
        return false;
    }

    // Sensor del XIAO Sense viene montado del reves: voltear horizontal+vertical
    // y subir un poco la saturacion para que el modelo distinga mejor objetos.
    sensor_t* sensor = esp_camera_sensor_get();
    if (sensor) {
        sensor->set_vflip(sensor, 1);     // 1 = flip vertical
        sensor->set_hmirror(sensor, 1);   // 1 = espejo horizontal
        sensor->set_brightness(sensor, 1);
        sensor->set_saturation(sensor, 1);
        sensor->set_contrast(sensor, 1);
    }

    s_ready = true;
    Serial.println("[CAM] OV2640 ready (SVGA JPEG, flipped)");
    return true;
}

bool isVisionRequest(const String& userTextLower) {
#if !VISION_ENABLED
    return false;
#endif
    String triggers = VISION_TRIGGERS;
    triggers.toLowerCase();
    int start = 0;
    while (start < (int)triggers.length()) {
        int comma = triggers.indexOf(',', start);
        if (comma < 0) comma = triggers.length();
        String w = triggers.substring(start, comma);
        w.trim();
        if (w.length() > 0 && userTextLower.indexOf(w) >= 0) return true;
        start = comma + 1;
    }
    return false;
}

// --- Scene fingerprint state (cheap change detection) ---
static bool     s_haveFingerprint = false;
static uint32_t s_lastSize = 0;
static uint32_t s_lastHash = 0;
static String   s_lastDescription;

static String captureBase64() {
    if (!s_ready) {
        Serial.println("[CAM] not ready");
        return "";
    }

    // Throw away 3 frames so auto-exposure / white balance settle.
    for (int i = 0; i < 3; ++i) {
        camera_fb_t* warm = esp_camera_fb_get();
        if (warm) esp_camera_fb_return(warm);
    }

    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("[CAM] capture failed");
        return "";
    }
    Serial.printf("[CAM] captured %u bytes JPEG\n", (unsigned)fb->len);

    // Allocate base64 buffer in PSRAM. base64 grows ~4/3.
    size_t b64Cap = ((fb->len + 2) / 3) * 4 + 4;
    char* b64 = (char*)ps_malloc(b64Cap);
    if (!b64) {
        Serial.println("[CAM] ps_malloc base64 failed");
        esp_camera_fb_return(fb);
        return "";
    }
    size_t outLen = 0;
    int rc = mbedtls_base64_encode((unsigned char*)b64, b64Cap, &outLen,
                                   fb->buf, fb->len);
    esp_camera_fb_return(fb);
    if (rc != 0) {
        Serial.printf("[CAM] base64 failed %d\n", rc);
        free(b64);
        return "";
    }
    String out;
    out.reserve(outLen);
    out.concat(b64, outLen);
    free(b64);
    return out;
}

String describe(const String& prompt) {
#if !VISION_ENABLED
    return "";
#endif
    String b64 = captureBase64();
    if (b64.length() == 0) return "";

    WiFiClientSecure client;
    client.setInsecure();
    client.setHandshakeTimeout(30);
    HTTPClient http;
    if (!http.begin(client, "https://api.groq.com/openai/v1/chat/completions")) {
        Serial.println("[VIS] http.begin failed");
        return "";
    }
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", String("Bearer ") + GROQ_API_KEY);
    http.setTimeout(HTTP_TIMEOUT_MS);

    // Build the JSON manually because ArduinoJson would copy the huge base64.
    String userPrompt = prompt;
    if (userPrompt.length() == 0) userPrompt = "Describe brevemente lo que ves.";
    // Escape quotes/backslashes in user prompt for JSON safety.
    String safe;
    safe.reserve(userPrompt.length() + 8);
    for (size_t i = 0; i < userPrompt.length(); ++i) {
        char c = userPrompt[i];
        if (c == '"' || c == '\\') safe += '\\';
        if (c == '\n') { safe += "\\n"; continue; }
        if (c == '\r') continue;
        safe += c;
    }

    String payload;
    payload.reserve(b64.length() + 1024);
    payload  = "{\"model\":\"";
    payload += GROQ_VISION_MODEL;
    payload += "\",\"max_tokens\":80,\"temperature\":0.2,\"messages\":[";
    payload += "{\"role\":\"system\",\"content\":\"";
    payload += "Eres un descriptor objetivo. Responde en espanol en UNA sola frase muy corta, ";
    payload += "sin opinar, sin saludar, sin humor, sin metacomentarios. ";
    payload += "PROHIBIDO empezar con 'parece que', 'estoy viendo', 'veo', 'la imagen muestra' o similares: ";
    payload += "empieza directamente por el sujeto. ";
    payload += "Si no estas seguro, di 'no distingo bien X' pero sin adornos. ";
    payload += "Ejemplos validos: 'Un hombre moreno con camisa blanca delante de un monitor.' o ";
    payload += "'Una mano sosteniendo un objeto rectangular de madera clara.'";
    payload += "\"},";
    payload += "{\"role\":\"user\",\"content\":[";
    payload += "{\"type\":\"text\",\"text\":\"";
    payload += safe;
    payload += "\"},";
    payload += "{\"type\":\"image_url\",\"image_url\":{\"url\":\"data:image/jpeg;base64,";
    payload += b64;
    payload += "\"}}]}]}";

    Serial.printf("[VIS] POST payload=%u bytes\n", (unsigned)payload.length());
    int code = http.POST(payload);
    if (code != 200) {
        Serial.printf("[VIS] HTTP %d: %s\n", code, http.getString().c_str());
        http.end();
        return "";
    }
    String body = http.getString();
    http.end();

    JsonDocument resp;
    DeserializationError err = deserializeJson(resp, body);
    if (err) {
        Serial.printf("[VIS] JSON parse failed: %s\n", err.c_str());
        return "";
    }
    const char* content = resp["choices"][0]["message"]["content"] | "";
    Serial.printf("[VIS] -> %s\n", content);
    String reply(content);
    if (reply.length() > 0) s_lastDescription = reply;
    return reply;
}

bool sceneChanged() {
#if !VISION_ENABLED
    return false;
#endif
    if (!s_ready) return false;

    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("[CAM] fingerprint capture failed");
        return false;
    }

    // Cheap fingerprint: jpeg byte length + xor checksum of every 64th byte.
    uint32_t size = (uint32_t)fb->len;
    uint32_t hash = 0;
    for (size_t i = 0; i < fb->len; i += 64) {
        hash ^= ((uint32_t)fb->buf[i]) << ((i & 3) * 8);
    }
    esp_camera_fb_return(fb);

    bool changed = false;
    if (!s_haveFingerprint) {
        changed = true;  // first ever frame -> consider it new
    } else {
        // Size-based diff is the strongest signal for JPEG of static scenes.
        uint32_t sizeDiff = (size > s_lastSize) ? (size - s_lastSize)
                                                : (s_lastSize - size);
        // Threshold ~5% of previous size, with a small floor.
        uint32_t thr = s_lastSize / 20;
        if (thr < 800) thr = 800;
        if (sizeDiff > thr) changed = true;
        // Or hash differs in many bits.
        if (!changed) {
            uint32_t x = hash ^ s_lastHash;
            int bits = __builtin_popcount(x);
            if (bits > 6) changed = true;
        }
    }
    Serial.printf("[CAM] fp size=%u hash=%08x %s\n",
                  (unsigned)size, (unsigned)hash, changed ? "CHANGED" : "same");
    s_lastSize = size;
    s_lastHash = hash;
    s_haveFingerprint = true;
    return changed;
}

const String& lastDescription() {
    return s_lastDescription;
}

} // namespace vision
