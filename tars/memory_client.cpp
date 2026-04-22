#include "memory_client.h"
#include "config.h"

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

namespace mem {

static const char* MEM0_HOST = "https://api.mem0.ai";

static bool postJson(const char* path, const String& body, String& out) {
    WiFiClientSecure client;
    client.setInsecure();
    client.setHandshakeTimeout(20);

    HTTPClient http;
    String url = String(MEM0_HOST) + path;
    if (!http.begin(client, url)) {
        Serial.println("[MEM] http.begin failed");
        return false;
    }
    http.setTimeout(HTTP_TIMEOUT_MS);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", String("Token ") + MEM0_API_KEY);

    int code = http.POST(body);
    out = http.getString();
    http.end();

    if (code < 200 || code >= 300) {
        Serial.printf("[MEM] HTTP %d: %s\n", code, out.c_str());
        return false;
    }
    return true;
}

String recall(const String& query) {
#if !MEM0_ENABLED
    return "";
#endif
    JsonDocument req;
    req["query"]   = query;
    req["user_id"] = MEM0_USER_ID;
    req["limit"]   = MEM0_RECALL_LIMIT;

    String payload;
    serializeJson(req, payload);

    String body;
    if (!postJson("/v1/memories/search/", payload, body)) {
        return "";
    }

    JsonDocument resp;
    if (deserializeJson(resp, body)) {
        Serial.println("[MEM] recall JSON parse failed");
        return "";
    }

    // Mem0 a veces devuelve {"error": "..."} con HTTP 200; detectarlo.
    if (resp["error"].is<const char*>()) {
        Serial.printf("[MEM] Mem0 error: %s\n", resp["error"].as<const char*>());
        return "";
    }

    // Mem0 may return either an array or an object with "results".
    JsonArray arr;
    if (resp.is<JsonArray>()) {
        arr = resp.as<JsonArray>();
    } else if (resp["results"].is<JsonArray>()) {
        arr = resp["results"].as<JsonArray>();
    } else {
        return "";
    }

    String out;
    int n = 0;
    for (JsonVariant item : arr) {
        const char* m = item["memory"] | item["text"] | "";
        if (m && *m) {
            out += "- ";
            out += m;
            out += "\n";
            n++;
        }
    }
    Serial.printf("[MEM] recall: %d memories\n", n);
    return out;
}

bool remember(const String& userText, const String& assistantText) {
#if !MEM0_ENABLED
    return false;
#endif
    JsonDocument req;
    req["user_id"] = MEM0_USER_ID;

    JsonArray msgs = req["messages"].to<JsonArray>();
    JsonObject u = msgs.add<JsonObject>();
    u["role"]    = "user";
    u["content"] = userText;
    JsonObject a = msgs.add<JsonObject>();
    a["role"]    = "assistant";
    a["content"] = assistantText;

    String payload;
    serializeJson(req, payload);

    String body;
    bool ok = postJson("/v1/memories/", payload, body);
    if (ok) Serial.println("[MEM] remembered");
    return ok;
}

} // namespace mem
