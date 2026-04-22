#pragma once
#include <Arduino.h>

namespace tg {
    // Sends `text` to the configured TELEGRAM_CHAT_ID via Bot API.
    bool send(const String& text);
}
