#pragma once
#include <Arduino.h>

namespace vision {
    bool begin();

    // Returns true if `userText` contains any VISION_TRIGGERS keyword.
    bool isVisionRequest(const String& userTextLower);

    // Captures a JPEG from the OV2640, sends it to Groq vision with `prompt`,
    // returns the model's reply. Empty string on error.
    String describe(const String& prompt);

    // --- Cheap "is the world different now?" check ---
    // Captures a frame and compares its fingerprint (jpeg size + xor checksum
    // of every Nth byte) with the previous one. Returns true if the scene
    // looks different enough. Does NOT call any external API.
    // ~200 ms per call (just the camera capture).
    bool sceneChanged();

    // Last successful description from describe(). Empty until first call.
    const String& lastDescription();
}
