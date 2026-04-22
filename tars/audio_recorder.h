#pragma once
#include <Arduino.h>

namespace audio {
    bool begin();
    void waitForVoice();
    // Variant that gives up after `timeoutMs` of silence and returns false,
    // letting the caller run autonomy ticks. Returns true if voice detected.
    bool waitForVoiceTimeout(uint32_t timeoutMs);
    uint8_t* recordWav(size_t& outSize);
}
