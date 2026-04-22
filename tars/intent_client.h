#pragma once
#include <Arduino.h>

namespace intent {

enum Kind {
    CHAT = 0,    // conversacion normal, no es una orden
    COME,        // ven aqui / acercate
    STOP,        // para, quieto, detente
    REST,        // descansa, duerme, modo bajo
    PLAY,        // diviertete, juega, se creativo
    EXPLORE,     // explora, curiosea, sigue mirando
    LOOK         // mira / que ves / fijate (vision puntual)
};

struct Result {
    Kind   kind        = CHAT;
    String reply;       // respuesta corta hablada que TARS deberia dar (puede estar vacia)
    bool   addressed   = false;  // true si la frase iba DIRIGIDA a TARS (nombre, imperativo, pregunta al robot)
};

const char* name(Kind k);

// Llama a Groq para clasificar la frase del usuario en una intencion.
// Si falla la API, devuelve { CHAT, "" } para que la conversacion siga siendo normal.
Result classify(const String& userText);

} // namespace intent
