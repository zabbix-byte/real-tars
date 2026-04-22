#pragma once
#include <Arduino.h>

namespace groq {
    String transcribe(const uint8_t* wav, size_t wavSize);
    String ask(const String& userText, const String& memories = "");
}
