// =============================================================
//  TARS  (Arduino IDE sketch)
//  XIAO ESP32-S3 Sense | Groq Whisper + Llama | Telegram out
// =============================================================
//
//  REQUISITOS EN ARDUINO IDE:
//    1. File -> Preferences -> Additional Board Manager URLs, añade:
//       https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
//    2. Tools -> Board Manager -> instala "esp32 by Espressif" (>= 3.0.0)
//    3. Tools -> Board -> ESP32 Arduino -> "XIAO_ESP32S3"
//    4. Tools -> USB CDC On Boot: "Enabled"
//    5. Tools -> PSRAM: "OPI PSRAM"
//    6. Tools -> Partition Scheme: "Huge APP (3MB No OTA/1MB SPIFFS)"
//    7. Sketch -> Include Library -> Manage Libraries -> instala:
//         - ArduinoJson (by Benoit Blanchon)
//    8. Copia "config.h.example" -> "config.h" y rellena tus claves.
//    9. Upload.
//
//  Flow:
//    1. Boot -> WiFi connect -> init PDM mic
//    2. Wait for voice (simple amplitude VAD)
//    3. Record WAV until silence
//    4. Upload WAV -> Groq Whisper -> text
//    5. Send text -> Groq Llama (TARS persona) -> reply
//    6. Reply -> Telegram bot
//    7. Back to step 2
//
// =============================================================

#include <Arduino.h>
#include "config.h"
#include "wifi_manager.h"
#include "audio_recorder.h"
#include "groq_client.h"
#include "telegram_client.h"
#include "memory_client.h"
#include "vision_client.h"
#include "behavior_state.h"
#include "intent_client.h"
#include "actions.h"
#include "autonomy.h"
#include "brain_context.h"

static void banner() {
    Serial.println();
    Serial.println(F("=============================================="));
    Serial.println(F("   TARS"));
    Serial.println(F("   Interstellar-inspired sarcastic robot"));
    Serial.println(F("=============================================="));
    Serial.printf ("  Humor level: %d%%\n", TARS_HUMOR_LEVEL);
    Serial.printf ("  STT model  : %s\n", GROQ_STT_MODEL);
    Serial.printf ("  LLM model  : %s\n", GROQ_LLM_MODEL);
    Serial.println(F("==============================================="));
}

void setup() {
    Serial.begin(115200);
    delay(1500);
    banner();

    if (!psramFound()) {
        Serial.println(F("[FATAL] PSRAM not detected. Tools -> PSRAM: OPI PSRAM"));
        while (true) delay(1000);
    }

    if (!wifi_mgr::connect()) {
        Serial.println(F("[FATAL] WiFi failed. Check config.h."));
        while (true) delay(1000);
    }

    if (!audio::begin()) {
        Serial.println(F("[FATAL] Audio init failed."));
        while (true) delay(1000);
    }

    // Camera is optional; if it fails we just log and continue without vision.
    if (!vision::begin()) {
        Serial.println(F("[WARN] Camera init failed; vision disabled."));
    }

    // Objetivos iniciales del robot. El LLM los ve cuando responde y los
    // usa para decidir a que prestar atencion. Puedes a\u00f1adir/quitar en caliente.
    brain::addGoal("conocer mejor a tu humano observando como trabaja");
    brain::addGoal("fijarte en objetos nuevos que no hayas registrado antes");
    brain::addGoal("no repetir el mismo comentario dos veces");
    brain::logMental("arranque del sistema");

    Serial.println(F("TARS online. Speak to me. Or don't. I'm a robot."));
}

// ---------- helpers ----------

static bool containsWakeWord(const String& low) {
#if !REQUIRE_WAKE_WORD
    return true;
#endif
    String words = WAKE_WORDS;
    words.toLowerCase();
    int start = 0;
    while (start < (int)words.length()) {
        int comma = words.indexOf(',', start);
        if (comma < 0) comma = words.length();
        String w = words.substring(start, comma);
        w.trim();
        if (w.length() > 0 && low.indexOf(w) >= 0) return true;
        start = comma + 1;
    }
    return false;
}

static bool isHallucination(const String& low) {
    static const char* H[] = {
        "thank you", "thanks for watching", "thanks", "you",
        "gracias", "subtitles by", "bye", ".", "..", "...",
        "amara.org", "transcription by", "music"
    };
    for (auto h : H) {
        if (low == h || low == String(h) + ".") return true;
    }
    return false;
}

// Apply intent: change state, run physical stub, return optional spoken reply.
static String applyIntent(intent::Kind k) {
    using namespace intent;
    switch (k) {
        case COME:    actions::approachUser(); behavior::set(behavior::COME,   "intent COME"); break;
        case STOP:    actions::halt();         behavior::set(behavior::IDLE,   "intent STOP"); break;
        case REST:    actions::sleep();        behavior::set(behavior::REST,   "intent REST"); break;
        case PLAY:    actions::playMode();     behavior::set(behavior::PLAY,   "intent PLAY"); break;
        case EXPLORE: actions::wander();       behavior::set(behavior::EXPLORE,"intent EXPLORE"); break;
        case LOOK:    actions::lookHere();     /* state unchanged */ break;
        case CHAT:    /* nothing */ break;
    }
    return "";
}

// Process one captured + transcribed user utterance.
static void handleUserText(const String& userText) {
    String low = userText;
    low.toLowerCase();

    if (isHallucination(low)) {
        Serial.printf("[loop] Whisper hallucination ignored: %s\n", userText.c_str());
        return;
    }

    Serial.printf("[USER ] %s\n", userText.c_str());

    // 1. Clasificar SIEMPRE. Ademas de la intencion, el clasificador nos dice
    //    si la frase iba dirigida al robot (addressed).
    intent::Result it = intent::classify(userText);

    // 2. Puerta de entrada a la conversacion:
    //    - si ya estamos en CHAT, aceptamos sin mas (conversacion en curso)
    //    - si no, hace falta palabra de activacion O que el clasificador
    //      considere que la frase iba dirigida a TARS.
    bool inChat    = (behavior::current() == behavior::CHAT);
    bool hasWake   = containsWakeWord(low);
    bool accept    = inChat || hasWake || it.addressed;
    if (!accept) {
        Serial.println(F("[loop] No dirigido a TARS, ignorado."));
        return;
    }

    // Entrar / refrescar CHAT.
    behavior::State prev = behavior::current();
    behavior::set(behavior::CHAT, "user spoke");
    behavior::touchConversation();
    if (prev != behavior::CHAT) brain::clearConversation();  // nueva conversacion

    // Registrar lo que dijo el humano en el contexto corto.
    brain::pushUser(userText);

    // 3. Si es una orden de comportamiento, aplicarla y usar la reply corta.
    String reply;
    if (it.kind != intent::CHAT && it.kind != intent::LOOK) {
        applyIntent(it.kind);
        reply = it.reply;
        brain::logMental(String("orden recibida: ") + intent::name(it.kind));
    }

    // 4. LOOK o CHAT: producir respuesta real.
    if (reply.length() == 0) {
        String memories = mem::recall(userText);
        if (it.kind == intent::LOOK || vision::isVisionRequest(low)) {
            Serial.println(F("[loop] Vision branch."));
            // Si el bucle de exploracion YA vio algo hace poco, reutilizamos ese frame
            // (evita re-capturar y re-subir cuando TARS ya esta mirando en tiempo real).
            String seen;
            const unsigned long VISION_CACHE_FRESH_MS = 4000;
            if (brain::lastVisionAgeMs() < VISION_CACHE_FRESH_MS) {
                seen = brain::lastVision();
                Serial.printf("[loop] Reusando vision reciente (%lums): %s\n",
                              brain::lastVisionAgeMs(), seen.c_str());
            } else {
                seen = vision::describe("Describe brevemente lo principal de la imagen.");
                if (seen.length() > 0) {
                    brain::setLastVision(seen);
                    brain::logMental(String("acabo de mirar y veo: ") + seen);
                }
            }
            if (seen.length() > 0) {
                // TARS reacciona a lo que SUS ojos han visto, con personalidad y memoria.
                String fused = String("El humano me dice: \"") + userText +
                    "\". Mis ojos ven ahora mismo: \"" + seen +
                    "\". Responde COMO TARS, como si lo vieras tu, sin decir 'parece que veo' ni 'la imagen muestra'. Reacciona en 1-2 frases con tu humor.";
                reply = groq::ask(fused, memories);
            }
        }
        if (reply.length() == 0) {
            reply = groq::ask(userText, memories);
        }
    }

    reply.trim();
    if (reply.length() == 0) {
        Serial.println(F("[loop] No reply produced."));
        return;
    }
    Serial.printf("[TARS ] %s\n", reply.c_str());
    tg::send(reply);
    brain::pushAssistant(reply);
    mem::remember(userText, reply);

    Serial.println(F("---------- ready ----------"));
}

void loop() {
    wifi_mgr::ensureConnected();
    behavior::tickChatTimeout();

    // Sliced wait for voice so we can interleave autonomy ticks.
    bool gotVoice = audio::waitForVoiceTimeout(VOICE_WAIT_SLICE_MS);

    if (gotVoice) {
        size_t wavSize = 0;
        uint8_t* wav = audio::recordWav(wavSize);
        if (!wav || wavSize == 0) {
            Serial.println(F("[loop] No audio captured."));
            if (wav) free(wav);
            return;
        }
        String userText = groq::transcribe(wav, wavSize);
        free(wav);
        userText.trim();
        if (userText.length() >= 2) {
            handleUserText(userText);
        }
        return;
    }

    // No voice this slice -> autonomy.
#if BEHAVIOR_ENABLED
    behavior::State st = behavior::current();
    if (st == behavior::CHAT) {
        // Mientras hablamos, la camara sigue atenta para ver si el humano se va.
        autonomy::presenceTick();
    } else {
        if (behavior::shouldExploreNow()) {
            autonomy::exploreTick();
            behavior::markExplored();
        }
        if (behavior::shouldPlayNow()) {
            autonomy::playTick();
            behavior::markPlayed();
        }
    }
#endif
}
