#include "brain_context.h"
#include "config.h"
#include "behavior_state.h"

#include <time.h>

namespace brain {

// ------------------------------------------------------------------
// Conversacion corta: ring buffer de turnos
// ------------------------------------------------------------------
#define BRAIN_CONV_MAX   6   // parejas user+assistant

struct Turn {
    char role;       // 'U' user, 'A' assistant
    String text;
};
static Turn     s_conv[BRAIN_CONV_MAX * 2];
static uint8_t  s_convCount = 0;   // total ocupado (<= BRAIN_CONV_MAX*2)
static uint8_t  s_convHead  = 0;   // proximo hueco (ring)

static void pushTurn(char role, const String& t) {
    s_conv[s_convHead].role = role;
    s_conv[s_convHead].text = t;
    s_convHead = (s_convHead + 1) % (BRAIN_CONV_MAX * 2);
    if (s_convCount < BRAIN_CONV_MAX * 2) s_convCount++;
}

void pushUser(const String& text)      { pushTurn('U', text); }
void pushAssistant(const String& text) { pushTurn('A', text); }

void clearConversation() {
    s_convCount = 0;
    s_convHead  = 0;
}

bool hasConversation() { return s_convCount > 0; }

String conversationBlock() {
    if (s_convCount == 0) return "";
    String out;
    out.reserve(s_convCount * 40);
    uint8_t start = (s_convHead + (BRAIN_CONV_MAX * 2) - s_convCount) % (BRAIN_CONV_MAX * 2);
    for (uint8_t i = 0; i < s_convCount; ++i) {
        const Turn& t = s_conv[(start + i) % (BRAIN_CONV_MAX * 2)];
        out += (t.role == 'U') ? "USER: " : "TARS: ";
        out += t.text;
        out += '\n';
    }
    return out;
}

// ------------------------------------------------------------------
// Vision reciente
// ------------------------------------------------------------------
static String   s_lastVision;
static uint32_t s_lastVisionMs = 0;

void setLastVision(const String& desc) {
    s_lastVision   = desc;
    s_lastVisionMs = millis();
}

String lastVision() { return s_lastVision; }

uint32_t lastVisionAgeMs() {
    if (s_lastVisionMs == 0) return UINT32_MAX;
    return millis() - s_lastVisionMs;
}

// ------------------------------------------------------------------
// Mental log
// ------------------------------------------------------------------
#define BRAIN_LOG_MAX   8

struct LogEntry {
    String   text;
    uint32_t ms = 0;
};
static LogEntry s_log[BRAIN_LOG_MAX];
static uint8_t  s_logCount = 0;
static uint8_t  s_logHead  = 0;

static bool similar(const String& a, const String& b) {
    // heuristica tonta pero util: si comparten >=3 palabras de >=5 letras
    // consideramos que es lo mismo.
    String la = a; la.toLowerCase();
    String lb = b; lb.toLowerCase();
    int common = 0;
    int from = 0;
    while (from < (int)la.length()) {
        int sp = la.indexOf(' ', from);
        int end = (sp < 0) ? la.length() : sp;
        if (end - from >= 5) {
            String w = la.substring(from, end);
            if (lb.indexOf(w) >= 0) common++;
            if (common >= 3) return true;
        }
        from = (sp < 0) ? la.length() : sp + 1;
    }
    return false;
}

void logMental(const String& action) {
    s_log[s_logHead].text = action;
    s_log[s_logHead].ms   = millis();
    s_logHead = (s_logHead + 1) % BRAIN_LOG_MAX;
    if (s_logCount < BRAIN_LOG_MAX) s_logCount++;
    Serial.printf("[BRAIN] log: %s\n", action.c_str());
}

bool recentlyDidSimilar(const String& action, uint32_t withinMs) {
    uint32_t now = millis();
    for (uint8_t i = 0; i < s_logCount; ++i) {
        const LogEntry& e = s_log[i];
        if (e.ms == 0) continue;
        if ((now - e.ms) > withinMs) continue;
        if (similar(e.text, action)) return true;
    }
    return false;
}

String mentalLogBlock() {
    if (s_logCount == 0) return "";
    String out;
    uint32_t now = millis();
    // mas reciente primero
    for (int i = 0; i < s_logCount; ++i) {
        int idx = (s_logHead - 1 - i + BRAIN_LOG_MAX) % BRAIN_LOG_MAX;
        const LogEntry& e = s_log[idx];
        if (e.ms == 0) continue;
        uint32_t ageS = (now - e.ms) / 1000;
        out += "- hace ";
        out += ageS;
        out += "s: ";
        out += e.text;
        out += '\n';
    }
    return out;
}

// ------------------------------------------------------------------
// Goals
// ------------------------------------------------------------------
#define BRAIN_GOAL_MAX 6
static Goal s_goals[BRAIN_GOAL_MAX];

void addGoal(const String& text) {
    for (int i = 0; i < BRAIN_GOAL_MAX; ++i) {
        if (s_goals[i].text.length() == 0) {
            s_goals[i].text      = text;
            s_goals[i].createdMs = millis();
            s_goals[i].done      = false;
            Serial.printf("[BRAIN] goal +: %s\n", text.c_str());
            return;
        }
    }
    Serial.println("[BRAIN] goal list full, dropping");
}

void completeGoal(const String& matchSubstring) {
    String m = matchSubstring; m.toLowerCase();
    for (int i = 0; i < BRAIN_GOAL_MAX; ++i) {
        if (s_goals[i].text.length() == 0 || s_goals[i].done) continue;
        String t = s_goals[i].text; t.toLowerCase();
        if (t.indexOf(m) >= 0) {
            s_goals[i].done = true;
            Serial.printf("[BRAIN] goal done: %s\n", s_goals[i].text.c_str());
        }
    }
}

String goalsBlock() {
    String out;
    for (int i = 0; i < BRAIN_GOAL_MAX; ++i) {
        if (s_goals[i].text.length() == 0 || s_goals[i].done) continue;
        out += "- ";
        out += s_goals[i].text;
        out += '\n';
    }
    return out;
}

// ------------------------------------------------------------------
// System prompt dinamico
// ------------------------------------------------------------------
static String timeString() {
    time_t now = time(nullptr);
    if (now < 100000) return "";  // NTP no sincronizado aun
    struct tm t;
    localtime_r(&now, &t);
    char buf[48];
    static const char* dias[] = {"domingo","lunes","martes","miercoles","jueves","viernes","sabado"};
    snprintf(buf, sizeof(buf), "%s %02d:%02d", dias[t.tm_wday], t.tm_hour, t.tm_min);
    return String(buf);
}

// Tono segun franja horaria: tine el humor sin forzarlo.
static const char* moodByHour() {
    time_t now = time(nullptr);
    if (now < 100000) return nullptr;
    struct tm t;
    localtime_r(&now, &t);
    int h = t.tm_hour;
    if (h >= 0 && h < 6)   return "es de madrugada y estas medio adormilado, habla mas bajo y filosofico";
    if (h >= 6 && h < 10)  return "es por la manana temprano, vas recalentando circuitos, un poco rezongon";
    if (h >= 10 && h < 14) return "media manana, estas activo y observador";
    if (h >= 14 && h < 17) return "primera tarde, modestamente vago, humor seco";
    if (h >= 17 && h < 21) return "tarde avanzada, mas charlatan y curioso de lo normal";
    return "es de noche, en modo reflexivo, comentas cosas raras";
}

String buildSystemPrompt(const String& memories) {
    String out;
    out.reserve(1024);

    // 1. Persona.
    out += TARS_SYSTEM_PROMPT;

    // 2. Estado situacional.
    out += "\n\n[ESTADO INTERNO]\n";
    out += "- estado: ";
    out += behavior::name(behavior::current());
    out += '\n';
    String ts = timeString();
    if (ts.length() > 0) {
        out += "- hora: ";
        out += ts;
        out += '\n';
    }
    const char* mood = moodByHour();
    if (mood) {
        out += "- animo: ";
        out += mood;
        out += '\n';
    }

    // 3. Vision reciente (solo si es fresca).
    if (s_lastVision.length() > 0 && lastVisionAgeMs() < 120000UL) {
        out += "- ahora ves: ";
        out += s_lastVision;
        out += '\n';
    }

    // 4. Goals activos.
    String g = goalsBlock();
    if (g.length() > 0) {
        out += "\n[OBJETIVOS ACTIVOS]\n";
        out += g;
    }

    // 5. Log mental.
    String ml = mentalLogBlock();
    if (ml.length() > 0) {
        out += "\n[LO QUE HAS HECHO RECIENTEMENTE - no te repitas]\n";
        out += ml;
    }

    // 6. Memoria largo plazo.
    if (memories.length() > 0) {
        out += "\n[RECUERDOS DE TU HUMANO - uselos con naturalidad, sin citarlos]\n";
        out += memories;
    }

    // 7. Conversacion corta.
    String conv = conversationBlock();
    if (conv.length() > 0) {
        out += "\n[CONVERSACION RECIENTE]\n";
        out += conv;
    }

    // 8. Reglas de salida.
    out += "\n[COMO HABLAR AHORA]\n"
           "- Una o dos frases como mucho. Naturales, no plantillas.\n"
           "- Humor seco de verdad. Si no sale bueno, no lo fuerces: se conciso.\n"
           "- Nada de saludos ('Hola!', 'Claro!') ni muletillas de asistente.\n"
           "- Si ya has dicho algo parecido en tu log reciente, reconocelo con ironia en vez de repetirlo.\n"
           "- Si ves algo en [ESTADO INTERNO > ahora ves], habla de eso como si lo vieras tus ojos, no como una imagen.\n"
           "- Si no sabes, dilo en tu tono: 'ni idea', 'no me suena', antes de inventar.\n"
           "- Si se te ocurre una pregunta rara sobre lo que esta pasando, suelta una, no todas.\n";

    return out;
}

} // namespace brain
