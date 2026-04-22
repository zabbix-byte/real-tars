#include "groq_client.h"
#include "config.h"
#include "brain_context.h"

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

namespace groq {

static const char* GROQ_HOST = "api.groq.com";

String transcribe(const uint8_t* wav, size_t wavSize) {
    // DNS sanity check
    IPAddress ip;
    if (!WiFi.hostByName(GROQ_HOST, ip)) {
        Serial.println("[STT] DNS lookup FAILED");
        return "";
    }
    Serial.printf("[STT] %s -> %s\n", GROQ_HOST, ip.toString().c_str());

    WiFiClientSecure client;
    client.setInsecure();
    client.setHandshakeTimeout(30);
    client.setTimeout(15);

    bool connected = false;
    for (int attempt = 1; attempt <= 3 && !connected; ++attempt) {
        Serial.printf("[STT] connecting (attempt %d), free heap=%u...\n",
                      attempt, (unsigned)ESP.getFreeHeap());
        // Connect by hostname (NOT ip) so TLS SNI works on Cloudflare.
        if (client.connect(GROQ_HOST, 443)) {
            connected = true;
            break;
        }
        Serial.println("[STT] connect failed, retrying...");
        delay(1000);
    }
    if (!connected) {
        Serial.println("[STT] connect failed after retries");
        return "";
    }

    const char* boundary = "----TARS-Boundary-7f3e2a1b";
    String head;
    head.reserve(512);

    head += "--"; head += boundary; head += "\r\n";
    head += "Content-Disposition: form-data; name=\"model\"\r\n\r\n";
    head += GROQ_STT_MODEL; head += "\r\n";

    head += "--"; head += boundary; head += "\r\n";
    head += "Content-Disposition: form-data; name=\"language\"\r\n\r\n";
    head += "es\r\n";

    head += "--"; head += boundary; head += "\r\n";
    head += "Content-Disposition: form-data; name=\"temperature\"\r\n\r\n";
    head += "0\r\n";

    head += "--"; head += boundary; head += "\r\n";
    head += "Content-Disposition: form-data; name=\"response_format\"\r\n\r\n";
    head += "json\r\n";

    head += "--"; head += boundary; head += "\r\n";
    head += "Content-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\n";
    head += "Content-Type: audio/wav\r\n\r\n";

    String tail = "\r\n--";
    tail += boundary;
    tail += "--\r\n";

    size_t total = head.length() + wavSize + tail.length();

    client.printf("POST /openai/v1/audio/transcriptions HTTP/1.1\r\n");
    client.printf("Host: %s\r\n", GROQ_HOST);
    client.printf("Authorization: Bearer %s\r\n", GROQ_API_KEY);
    client.printf("Content-Type: multipart/form-data; boundary=%s\r\n", boundary);
    client.printf("Content-Length: %u\r\n", (unsigned)total);
    client.printf("Connection: close\r\n\r\n");

    client.print(head);

    const size_t CHUNK = 1024;
    size_t sent = 0;
    while (sent < wavSize) {
        size_t n = (wavSize - sent) > CHUNK ? CHUNK : (wavSize - sent);
        client.write(wav + sent, n);
        sent += n;
    }
    client.print(tail);

    uint32_t deadline = millis() + HTTP_TIMEOUT_MS;
    while (client.connected() && !client.available() && millis() < deadline) {
        delay(10);
    }

    String status = client.readStringUntil('\n');
    // Parse proper HTTP status: "HTTP/1.1 200 OK" -> 3-digit code after the space.
    int spaceIdx = status.indexOf(' ');
    int httpCode = 0;
    if (spaceIdx > 0 && (int)status.length() >= spaceIdx + 4) {
        httpCode = status.substring(spaceIdx + 1, spaceIdx + 4).toInt();
    }
    if (httpCode != 200) {
        Serial.printf("[STT] HTTP error: %s\n", status.c_str());
        client.stop();
        return "";
    }

    while (client.connected()) {
        String line = client.readStringUntil('\n');
        if (line == "\r" || line.length() <= 1) break;
    }

    String body;
    while (client.connected() || client.available()) {
        while (client.available()) body += (char)client.read();
    }
    client.stop();

    JsonDocument doc;
    if (deserializeJson(doc, body)) {
        Serial.printf("[STT] JSON parse failed: %s\n", body.c_str());
        return "";
    }
    const char* text = doc["text"] | "";
    Serial.printf("[STT] -> %s\n", text);
    return String(text);
}

String ask(const String& userText, const String& memories) {
    WiFiClientSecure client;
    client.setInsecure();
    HTTPClient http;

    if (!http.begin(client, "https://api.groq.com/openai/v1/chat/completions")) {
        Serial.println("[LLM] http.begin failed");
        return "";
    }

    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", String("Bearer ") + GROQ_API_KEY);
    http.setTimeout(HTTP_TIMEOUT_MS);

    JsonDocument req;
    req["model"]       = GROQ_LLM_MODEL;
    req["temperature"] = 0.8;
    req["max_tokens"]  = 80;

    // System prompt dinamico: persona + estado + vision + memorias + log + conversacion.
    String sysContent = brain::buildSystemPrompt(memories);

    JsonArray msgs = req["messages"].to<JsonArray>();
    JsonObject sys = msgs.add<JsonObject>();
    sys["role"]    = "system";
    sys["content"] = sysContent;
    JsonObject usr = msgs.add<JsonObject>();
    usr["role"]    = "user";
    usr["content"] = userText;

    String payload;
    serializeJson(req, payload);

    int code = http.POST(payload);
    if (code != 200) {
        Serial.printf("[LLM] HTTP %d: %s\n", code, http.getString().c_str());
        http.end();
        // Fallback con voz propia en vez de silencio. No decimos "error" ni "API":
        // lo oye el humano en Telegram como si fuera TARS hablando.
        if (code == 429) return "Se me ha cruzado un cable, dame un segundo.";
        if (code >= 500) return "Los de Groq estan teniendo una mala tarde. Vuelve a intentarlo.";
        if (code <= 0)   return "Se me fue el wifi, literal. Repite?";
        return "";
    }

    String body = http.getString();
    http.end();

    JsonDocument resp;
    if (deserializeJson(resp, body)) {
        Serial.println("[LLM] JSON parse failed");
        return "";
    }
    const char* content = resp["choices"][0]["message"]["content"] | "";
    Serial.printf("[LLM] -> %s\n", content);
    return String(content);
}

} // namespace groq
