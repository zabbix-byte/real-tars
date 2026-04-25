#include "gemini_client.h"
#include "config.h"
#include "brain_context.h"
#include "vision_client.h"

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

namespace gemini {

// Escapa comillas/backslashes/saltos de linea para meter el texto "tal cual"
// dentro de un string JSON que construimos a mano (para NO copiar el base64
// enorme dentro de un ArduinoJson JsonDocument -> OOM).
static void appendJsonEscaped(String& out, const String& in) {
    for (size_t i = 0; i < in.length(); ++i) {
        char c = in[i];
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n";  break;
            case '\r':               break;  // ignoramos CR
            case '\t': out += "\\t";  break;
            default:
                if ((unsigned char)c < 0x20) {
                    char buf[8];
                    snprintf(buf, sizeof(buf), "\\u%04x", c);
                    out += buf;
                } else {
                    out += c;
                }
        }
    }
}

String ask(const String& userText, const String& memories, bool withImage) {
#if !GEMINI_ENABLED
    return "";
#endif

    // 1) Capturar frames SOLO si nos lo piden y la camara funciona.
    //    Ráfaga de N frames espaciados -> Gemini los interpreta como
    //    secuencia temporal (ve movimiento, no foto muerta).
    int   nFrames = 0;
    String b64s[8];   // soportamos hasta 8 frames maximo
    if (withImage) {
        int want = GEMINI_BURST_FRAMES;
        if (want < 1) want = 1;
        if (want > 8) want = 8;
        for (int i = 0; i < want; ++i) {
            String b = vision::captureJpegBase64();
            if (b.length() == 0) {
                Serial.printf("[GEM] frame %d fallo; sigo con los que tenga\n", i);
                break;
            }
            b64s[nFrames++] = b;
            if (i < want - 1) {
                delay(GEMINI_BURST_INTERVAL_MS);
            }
        }
        if (nFrames == 0) {
            Serial.println("[GEM] sin imagen (camara no disponible), sigo solo con texto");
        } else {
            Serial.printf("[GEM] rafaga capturada: %d frames\n", nFrames);
        }
    }

    // 2) System prompt dinamico con persona + estado + memorias + conversacion.
    String sys = brain::buildSystemPrompt(memories);
    // Refuerzo anti-alucinacion: si hay imagen, decirle que describa SOLO lo
    // que ve; si no hay, que no invente escena.
    if (nFrames > 0) {
        sys += "\n\nTienes VISION EN VIVO. En este turno te adjunto ";
        sys += String(nFrames);
        sys += " frames JPEG capturados por la camara del robot en los ultimos ";
        sys += String((nFrames - 1) * GEMINI_BURST_INTERVAL_MS);
        sys += " ms, en orden cronologico (el primero es el mas antiguo). "
               "Interpretalo como un VIDEO CORTO: puedes comentar movimiento, "
               "gestos o cambios entre frames. Describe SOLO lo que aparece. "
               "No inventes personas ni objetos. Si no distingues algo, dilo. "
               "No repitas descripciones de turnos anteriores.";
    } else {
        sys += "\n\nAhora mismo no tienes vision. Si te preguntan que ves, di que "
               "no estas viendo. No inventes escena.";
    }

    // 3) Construir JSON a mano para evitar copias del base64.
    String url = "https://generativelanguage.googleapis.com/v1beta/models/";
    url += GEMINI_MODEL;
    url += ":generateContent?key=";
    url += GEMINI_API_KEY;

    WiFiClientSecure client;
    client.setInsecure();
    client.setHandshakeTimeout(30);
    HTTPClient http;
    if (!http.begin(client, url)) {
        Serial.println("[GEM] http.begin failed");
        return "";
    }
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(HTTP_TIMEOUT_MS);

    String payload;
    size_t totalB64 = 0;
    for (int i = 0; i < nFrames; ++i) totalB64 += b64s[i].length();
    payload.reserve(totalB64 + sys.length() + userText.length() + 1024);

    payload  = "{\"system_instruction\":{\"parts\":[{\"text\":\"";
    appendJsonEscaped(payload, sys);
    payload += "\"}]},\"contents\":[{\"role\":\"user\",\"parts\":[";

    // texto del usuario
    payload += "{\"text\":\"";
    appendJsonEscaped(payload, userText);
    payload += "\"}";

    // imagenes (ráfaga)
    for (int i = 0; i < nFrames; ++i) {
        payload += ",{\"inline_data\":{\"mime_type\":\"image/jpeg\",\"data\":\"";
        payload += b64s[i];
        payload += "\"}}";
        // liberamos ya este frame para recuperar PSRAM cuanto antes
        b64s[i] = String();
    }

    payload += "]}],\"generationConfig\":{\"temperature\":0.7,\"maxOutputTokens\":120,";
    payload += "\"topP\":0.9}}";

    Serial.printf("[GEM] POST payload=%u bytes (frames=%d)\n",
                  (unsigned)payload.length(), nFrames);

    int code = http.POST(payload);
    if (code != 200) {
        String err = http.getString();
        Serial.printf("[GEM] HTTP %d: %s\n", code, err.c_str());
        http.end();
        if (code == 429) return "Se me ha cruzado un cable, dame un segundo.";
        if (code >= 500) return "Los servidores estan malditos ahora mismo.";
        if (code <= 0)   return "Se me fue el wifi, literal. Repite?";
        return "";
    }

    String body = http.getString();
    http.end();

    // Respuesta tipica: {"candidates":[{"content":{"parts":[{"text":"..."}]}}]}
    JsonDocument resp;
    DeserializationError e = deserializeJson(resp, body);
    if (e) {
        Serial.printf("[GEM] JSON parse failed: %s\n", e.c_str());
        return "";
    }
    const char* text = resp["candidates"][0]["content"]["parts"][0]["text"] | "";
    String reply(text);
    reply.trim();
    Serial.printf("[GEM] -> %s\n", reply.c_str());
    return reply;
}

} // namespace gemini
