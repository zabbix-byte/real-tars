#pragma once
#include <Arduino.h>

namespace behavior {

enum State {
    EXPLORE = 0,   // default: observa el entorno, toma fotos, aprende novedades
    CHAT,          // acaba de hablar contigo, esta atento a la conversacion
    COME,          // viene hacia ti (placeholder, requiere ruedas)
    IDLE,          // espera quieto, sin explorar
    REST,          // bajo consumo, solo escucha si le hablan
    PLAY           // bromista, comenta cosas espontaneas en Telegram
};

const char* name(State s);

State current();
void   set(State next, const char* reason);

// Devuelve true si TARS deberia ejecutar un tic de exploracion ahora.
bool shouldExploreNow();
void markExplored();

// Devuelve true si TARS deberia mandar un comentario espontaneo ahora (PLAY).
bool shouldPlayNow();
void markPlayed();

// Marca actividad de conversacion (resetea timer de CHAT_GRACE).
void touchConversation();

// Marca que un humano esta visible en camara ahora mismo (lo usa autonomy).
void noteHumanVisible();

// Si estamos en CHAT y ha pasado CHAT_GRACE_MS sin hablar, volver a EXPLORE.
// Tambien corta antes si ha pasado CHAT_ABANDON_MS sin voz Y sin humano visible.
void tickChatTimeout();

} // namespace behavior
