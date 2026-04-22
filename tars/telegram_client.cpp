#include "telegram_client.h"
#include "config.h"

#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

namespace tg {

bool send(const String& text) {
    if (!SEND_MESSAGE_TELEGRAM) {
        Serial.printf("[TG] Disabled in config; would have sent: %s\n", text.c_str());
        return true;
    }

    WiFiClientSecure client;
    client.setInsecure();
    client.setHandshakeTimeout(30);

    HTTPClient http;
    String url = "https://api.telegram.org/bot";
    url += TELEGRAM_BOT_TOKEN;
    url += "/sendMessage";

    if (!http.begin(client, url)) {
        Serial.println("[TG] http.begin failed");
        return false;
    }
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(HTTP_TIMEOUT_MS);

    JsonDocument doc;
    doc["chat_id"] = TELEGRAM_CHAT_ID;
    doc["text"]    = text;

    String payload;
    serializeJson(doc, payload);

    int code = http.POST(payload);
    String body = http.getString();
    http.end();

    if (code == 200) {
        Serial.println("[TG] Telegram sent OK");
        return true;
    }
    Serial.printf("[TG] HTTP %d: %s\n", code, body.c_str());
    return false;
}

} // namespace tg
