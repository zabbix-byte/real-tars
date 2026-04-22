#pragma once
#include <Arduino.h>

namespace mem {
    // Returns a short text block with the most relevant memories for `query`.
    // Empty string if disabled, no match, or error.
    String recall(const String& query);

    // Stores the (user, assistant) exchange so Mem0 can extract long-term facts.
    bool remember(const String& userText, const String& assistantText);
}
