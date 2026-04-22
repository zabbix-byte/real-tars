#pragma once
#include <Arduino.h>

// brain_context: el "estado mental" de TARS en vivo.
//   - short-term: ultimas N parejas de conversacion (se olvidan al salir de CHAT)
//   - mental log: ultimas acciones/observaciones propias (para auto-conciencia)
//   - last vision: descripcion mas reciente de la camara
//   - goals: objetivos activos del robot
//
// Este modulo no llama a nadie. Solo es un "cuaderno" que rellenan los demas y
// que el groq_client lee al construir el system prompt.

namespace brain {

// --- Conversacion corta (short-term memory) ---
void pushUser(const String& text);
void pushAssistant(const String& text);
void clearConversation();                 // llamar al salir de CHAT
String conversationBlock();               // formateado como "USER: ...\nTARS: ..."
bool hasConversation();

// --- Vision reciente ---
void setLastVision(const String& desc);   // la pone autonomy/vision
String lastVision();
uint32_t lastVisionAgeMs();

// --- Mental log ---
// Cada entrada es una accion propia: "comente sobre portatil", "fui a REST", ...
void logMental(const String& action);
String mentalLogBlock();                  // bullets cronologicos, el mas reciente primero
// Devuelve true si ya hay una entrada muy parecida en los ultimos `withinMs` ms.
bool recentlyDidSimilar(const String& action, uint32_t withinMs = 10UL * 60UL * 1000UL);

// --- Goals ---
struct Goal {
    String   text;
    uint32_t createdMs = 0;
    bool     done      = false;
};
void addGoal(const String& text);
void completeGoal(const String& matchSubstring);
String goalsBlock();

// --- Contexto completo ---
// Concatena persona + estado + hora + visión + memorias + goals + log + convo
// Si memories esta vacio se omite esa seccion. Si no hay convo, tambien.
// Esta es la funcion que usa groq_client::ask.
String buildSystemPrompt(const String& memories);

} // namespace brain
