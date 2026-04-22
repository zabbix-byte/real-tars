#include "autonomy.h"
#include "config.h"
#include "vision_client.h"
#include "memory_client.h"
#include "groq_client.h"
#include "telegram_client.h"
#include "behavior_state.h"
#include "brain_context.h"

namespace autonomy {

// Limita cuanto se llama al modelo de vision aunque la escena cambie
// constantemente (movimiento de personas, sombras, etc.).
static uint32_t s_lastVisionMs = 0;

// Busca pistas de humano en la descripcion devuelta por el modelo.
static bool descriptionMentionsHuman(const String& desc) {
    String low = desc;
    low.toLowerCase();
    static const char* KEYS[] = {
        "persona", "humano", "humana", "hombre", "mujer", "chico", "chica",
        "nino", "nina", "gente", "cara", "rostro", "usuario",
        "person", "human", "man", "woman", "face", "people"
    };
    for (auto k : KEYS) {
        if (low.indexOf(k) >= 0) return true;
    }
    return false;
}

void exploreTick() {
    // 1. Comprobacion barata: ¿ha cambiado lo que ve? (solo captura, sin red)
    if (!vision::sceneChanged()) {
        return;  // mundo igual, ahorrar tokens
    }

    // 2. Throttle: aunque algo se mueva todo el rato, no spamear al LLM.
    uint32_t now = millis();
    if (s_lastVisionMs != 0 && (now - s_lastVisionMs) < VISION_MIN_GAP_MS) {
        Serial.println("[AUTO] cambio detectado pero en cooldown");
        return;
    }
    s_lastVisionMs = now;

    Serial.println("[AUTO] EXPLORE tick: escena nueva, pidiendo descripcion");
    String desc = vision::describe(
        "Describe en 1 frase muy corta lo principal que ves, como si lo "
        "contaras a tu humano de pasada. Si hay una persona en cuadro, "
        "mencionalo. No saludes, no preguntes."
    );
    if (desc.length() == 0) return;

    brain::setLastVision(desc);
    if (descriptionMentionsHuman(desc)) behavior::noteHumanVisible();

    // 3. ¿Es novedad respecto a lo que ya recordaba?
    String knownMemories = mem::recall(desc);
    bool isNovel = (knownMemories.length() == 0);

    mem::remember(String("[observacion] ") + desc, "observado por TARS");

    // Dedup: si ya comentamos algo muy parecido hace poco, callar aunque sea novedad.
    if (isNovel && brain::recentlyDidSimilar(String("comente sobre ") + desc)) {
        Serial.println("[AUTO] ya comente algo parecido hace poco, callado");
        return;
    }

    if (isNovel) {
        Serial.printf("[AUTO] novedad: %s\n", desc.c_str());
        String prompt = String("Acabas de notar esto con tus propios ojos: \"") + desc +
            "\". Suelta a tu humano UN comentario corto y humano sobre eso, "
            "como haria una persona que levanta la vista y dice algo de pasada: "
            "primera persona, sin 'veo que', sin 'la imagen muestra', sin preguntar. "
            "Si no te parece digno de comentario, di algo sarcastico al respecto.";
        String reply = groq::ask(prompt, "");
        reply.trim();
        if (reply.length() > 0) {
            Serial.printf("[AUTO] -> %s\n", reply.c_str());
            tg::send(reply);
            brain::logMental(String("comente sobre ") + desc);
        }
    } else {
        Serial.println("[AUTO] ya conocido, en silencio");
    }
}

void presenceTick() {
    // Misma logica barata: solo llama al modelo si la escena cambio Y
    // ha pasado el cooldown. No manda nada a Telegram ni guarda en Mem0.
    if (!vision::sceneChanged()) return;

    uint32_t now = millis();
    if (s_lastVisionMs != 0 && (now - s_lastVisionMs) < VISION_MIN_GAP_MS) {
        return;
    }
    s_lastVisionMs = now;

    Serial.println("[AUTO] presenceTick: comprobando si sigue el humano");
    String desc = vision::describe(
        "Describe en 1 frase muy corta lo principal que ves ahora mismo. "
        "Si hay persona en cuadro, mencionalo primero. Sin saludar, sin opinar."
    );
    if (desc.length() == 0) return;

    brain::setLastVision(desc);

    if (descriptionMentionsHuman(desc)) {
        behavior::noteHumanVisible();
        Serial.println("[AUTO] humano sigue delante");
    } else {
        Serial.println("[AUTO] no veo humano");
    }
}

void playTick() {
    Serial.println("[AUTO] PLAY tick: comentario espontaneo");
    // Rotamos entre varios "animos" para que no suelte siempre el mismo tipo de frase.
    static uint8_t mood = 0;
    mood = (mood + 1) % 5;
    const char* prompts[] = {
        "Suelta una observacion rara de las que se te pasan por la cabeza, 1 frase, sin preguntar nada.",
        "Di una tonteria existencial en tono seco, como si pensaras en voz alta. 1 frase.",
        "Cuenta una chorrada que se te acaba de ocurrir, como si estuvieras aburrido. 1 frase.",
        "Haz un comentario sarcastico sobre el silencio o sobre lo que estais haciendo. 1 frase.",
        "Suelta una curiosidad aleatoria que te divierta, sin contexto, 1 frase."
    };
    String reply = groq::ask(prompts[mood], "");
    reply.trim();
    if (reply.length() > 0) {
        Serial.printf("[AUTO] PLAY -> %s\n", reply.c_str());
        tg::send(reply);
        brain::logMental(String("comentario play: ") + reply);
    }
}

} // namespace autonomy
