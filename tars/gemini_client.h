#pragma once
#include <Arduino.h>

// Cerebro principal de TARS con Gemini 2.0 Flash.
// - Multimodal nativo: texto + imagen en una sola llamada.
// - Rapido (< 1 s tipico) y con vision mucho mejor que un VLM 7B.
// - Si `withImage` es true, captura un JPEG fresco de la camara y lo
//   adjunta para que Gemini "vea en tiempo real" lo que ve el robot.
namespace gemini {
    String ask(const String& userText,
               const String& memories = "",
               bool withImage = true);
}
