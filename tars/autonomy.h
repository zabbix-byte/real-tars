#pragma once
#include <Arduino.h>

namespace autonomy {
    // Llama mientras estamos en EXPLORE y toca tic. Toma foto, describe,
    // compara con recuerdos previos y comenta por Telegram solo si es novedad.
    void exploreTick();

    // Llama mientras estamos en PLAY. Genera un comentario espontaneo y lo
    // manda a Telegram.
    void playTick();

    // Llama periodicamente mientras estamos en CHAT. Captura una foto barata
    // y, si la escena cambio, pide una descripcion corta SOLO para detectar
    // si el humano sigue en el encuadre. No manda nada a Telegram.
    void presenceTick();
}
