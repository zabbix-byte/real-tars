#include "intent_client.h"
#include "config.h"

#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

namespace intent {

const char* name(Kind k) {
    switch (k) {
        case CHAT:    return "CHAT";
        case COME:    return "COME";
        case STOP:    return "STOP";
        case REST:    return "REST";
        case PLAY:    return "PLAY";
        case EXPLORE: return "EXPLORE";
        case LOOK:    return "LOOK";
    }
    return "?";
}

static Kind parseKind(const char* s) {
    if (!s) return CHAT;
    if (!strcasecmp(s, "COME"))    return COME;
    if (!strcasecmp(s, "STOP"))    return STOP;
    if (!strcasecmp(s, "REST"))    return REST;
    if (!strcasecmp(s, "PLAY"))    return PLAY;
    if (!strcasecmp(s, "EXPLORE")) return EXPLORE;
    if (!strcasecmp(s, "LOOK"))    return LOOK;
    return CHAT;
}

Result classify(const String& userText) {
    Result r;

    WiFiClientSecure client;
    client.setInsecure();
    HTTPClient http;
    if (!http.begin(client, "https://api.groq.com/openai/v1/chat/completions")) {
        Serial.println("[INTENT] http.begin failed");
        return r;
    }
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", String("Bearer ") + GROQ_API_KEY);
    http.setTimeout(HTTP_TIMEOUT_MS);

    JsonDocument req;
    req["model"]       = GROQ_INTENT_MODEL;
    req["temperature"] = 0;
    req["max_tokens"]  = INTENT_MAX_TOKENS;
    req["response_format"]["type"] = "json_object";

    JsonArray msgs = req["messages"].to<JsonArray>();
    JsonObject sys = msgs.add<JsonObject>();
    sys["role"]    = "system";
    sys["content"] =
        "Eres el clasificador de intencion de TARS, un robot autonomo en espanol. "
        "Devuelve SOLO un objeto JSON valido con TRES campos: "
        "\"intent\", \"reply\" y \"addressed\". "
        "intent debe ser exactamente uno de: CHAT, COME, STOP, REST, PLAY, EXPLORE, LOOK. "
        "reply es lo que TARS contestaria en voz alta, en espanol, "
        "maximo 1 frase corta con humor seco. Para CHAT deja reply vacio (\"\"). "
        "addressed es true si la frase va DIRIGIDA al robot (lo llama por "
        "nombre TARS, le da una orden, le hace una pregunta directa, usa "
        "imperativo dirigido a el, le saluda, o el contexto deja claro que "
        "le habla a el). false si parece que habla con otra persona, habla "
        "solo, ve la tele, o simplemente se oyo ruido de fondo.\n"
        "Reglas de intent:\n"
        "- COME: el humano quiere que TARS venga, se acerque, lo siga, vaya hacia el. "
        "Ej: 'ven aqui', 'acercate', 'sigueme', 'aqui chico'.\n"
        "- STOP: para de hacer lo que sea o termina la interaccion. "
        "Ej: 'para', 'quieto', 'dejalo', 'basta', 'callate', 'dejame en paz', "
        "'vete', 'piérdete', 'no me molestes'.\n"
        "- REST: bajar a modo bajo, dejar de explorar. Ej: 'descansa', 'duerme', "
        "'apagate un rato', 'tranquilo', 'modo silencio'.\n"
        "- PLAY: diviertete, se creativo, anima la cosa. Ej: 'diviertete', 'haz algo gracioso', "
        "'animate', 'cuenta chistes', 'entretente'.\n"
        "- EXPLORE: vuelve a curiosear el entorno por tu cuenta. Ej: 'explora', "
        "'mira por ahi', 'curiosea', 'a tu rollo', 'haz lo tuyo'.\n"
        "- LOOK: mira esto concreto AHORA y dime que ves. Ej: 'mira esto', 'que ves', "
        "'fijate en mi mano', 'describe la mesa'.\n"
        "- CHAT: cualquier otra cosa que no sea una orden de comportamiento.\n"
        "Infieres todo del SENTIDO, no de palabras exactas.";

    JsonObject usr = msgs.add<JsonObject>();
    usr["role"]    = "user";
    usr["content"] = userText;

    String payload;
    serializeJson(req, payload);

    int code = http.POST(payload);
    if (code != 200) {
        Serial.printf("[INTENT] HTTP %d: %s\n", code, http.getString().c_str());
        http.end();
        return r;
    }
    String body = http.getString();
    http.end();

    JsonDocument resp;
    if (deserializeJson(resp, body)) {
        Serial.println("[INTENT] resp parse failed");
        return r;
    }
    const char* content = resp["choices"][0]["message"]["content"] | "";
    if (!*content) return r;

    JsonDocument inner;
    if (deserializeJson(inner, content)) {
        Serial.printf("[INTENT] inner JSON parse failed: %s\n", content);
        return r;
    }
    r.kind  = parseKind(inner["intent"] | "CHAT");
    r.reply = String((const char*)(inner["reply"] | ""));
    r.addressed = inner["addressed"] | false;
    Serial.printf("[INTENT] %s addressed=%d | reply=\"%s\"\n",
                  name(r.kind), (int)r.addressed, r.reply.c_str());
    return r;
}

} // namespace intent
