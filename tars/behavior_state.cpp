#include "behavior_state.h"
#include "config.h"
#include "brain_context.h"

namespace behavior {

static State    s_state          = EXPLORE;
static uint32_t s_lastExplore    = 0;
static uint32_t s_lastPlay       = 0;
static uint32_t s_lastConvo      = 0;
static uint32_t s_lastHumanSeen  = 0;

const char* name(State s) {
    switch (s) {
        case EXPLORE: return "EXPLORE";
        case CHAT:    return "CHAT";
        case COME:    return "COME";
        case IDLE:    return "IDLE";
        case REST:    return "REST";
        case PLAY:    return "PLAY";
    }
    return "?";
}

State current() { return s_state; }

void set(State next, const char* reason) {
    if (next == s_state) return;
    Serial.printf("[STATE] %s -> %s (%s)\n", name(s_state), name(next),
                  reason ? reason : "");
    State prev = s_state;
    s_state = next;
    uint32_t now = millis();
    if (next == EXPLORE) s_lastExplore = now;
    if (next == PLAY)    s_lastPlay    = now;
    if (next == CHAT) {
        // Arrancar los relojes al entrar: si no se inicializan aqui,
        // millis()-0 da un numero enorme y el timeout dispara al instante.
        s_lastConvo     = now;
        s_lastHumanSeen = now;
    }
    // Al salir de CHAT, la conversacion corta se olvida. Dejamos el mental
    // log y Mem0 intactos: ESO es la memoria de largo plazo.
    if (prev == CHAT && next != CHAT) {
        brain::clearConversation();
        brain::logMental(String("conversacion terminada (-> ") + name(next) + ")");
    }
    if (next == CHAT && prev != CHAT) {
        brain::logMental("empieza conversacion");
    }
}

bool shouldExploreNow() {
    if (s_state != EXPLORE) return false;
    return (millis() - s_lastExplore) >= EXPLORE_INTERVAL_MS;
}
void markExplored() { s_lastExplore = millis(); }

bool shouldPlayNow() {
    if (s_state != PLAY) return false;
    return (millis() - s_lastPlay) >= PLAY_INTERVAL_MS;
}
void markPlayed() { s_lastPlay = millis(); }

void touchConversation() { s_lastConvo = millis(); }

void noteHumanVisible() { s_lastHumanSeen = millis(); }

void tickChatTimeout() {
    if (s_state != CHAT) return;
    // Guard: si por alguna razon los relojes no estan inicializados, los pone al dia
    // sin disparar timeout inmediato.
    if (s_lastConvo == 0)     s_lastConvo     = millis();
    if (s_lastHumanSeen == 0) s_lastHumanSeen = millis();
    uint32_t silence = millis() - s_lastConvo;
    uint32_t noHuman = millis() - s_lastHumanSeen;
    if (silence >= CHAT_GRACE_MS) {
        set(EXPLORE, "chat grace expired");
        return;
    }
    // Salida temprana: el humano ni habla ni esta delante.
    if (silence >= CHAT_ABANDON_MS && noHuman >= CHAT_ABANDON_MS) {
        set(EXPLORE, "chat abandoned (no voice, no human)");
    }
}

} // namespace behavior
