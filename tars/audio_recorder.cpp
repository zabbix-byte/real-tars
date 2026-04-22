#include "audio_recorder.h"
#include "config.h"

#include <ESP_I2S.h>

namespace audio {

static I2SClass I2S;
static int16_t* s_pcm = nullptr;
static size_t   s_pcmCapacity = 0;

// Pre-roll ring buffer: keeps the last ~500 ms of audio always recorded so we
// don't miss the wake word. When VAD triggers we copy this into the start of
// the main recording buffer. 500 ms @ 16 kHz = 8000 samples = 16 KB.
static const size_t PREROLL_SAMPLES = 8000;
static int16_t* s_preroll = nullptr;
static size_t   s_prerollWrite = 0;   // next write index in ring
static bool     s_prerollFull = false;
static size_t   s_prerollCount = 0;   // valid samples copied into s_pcm by waitForVoice

// XIAO ESP32-S3 Sense onboard PDM microphone
static const int PDM_CLK_PIN  = 42;
static const int PDM_DATA_PIN = 41;

bool begin() {
    s_pcmCapacity = (size_t)SAMPLE_RATE * RECORD_SECONDS;
    s_pcm = (int16_t*)ps_malloc(s_pcmCapacity * sizeof(int16_t));
    if (!s_pcm) {
        Serial.println("[ERR] ps_malloc failed for audio buffer");
        return false;
    }

    s_preroll = (int16_t*)ps_malloc(PREROLL_SAMPLES * sizeof(int16_t));
    if (!s_preroll) {
        Serial.println("[ERR] ps_malloc failed for preroll buffer");
        free(s_pcm);
        s_pcm = nullptr;
        return false;
    }

    I2S.setPinsPdmRx(PDM_CLK_PIN, PDM_DATA_PIN);
    if (!I2S.begin(I2S_MODE_PDM_RX, SAMPLE_RATE,
                   I2S_DATA_BIT_WIDTH_16BIT,
                   I2S_SLOT_MODE_MONO)) {
        Serial.println("[ERR] I2S PDM begin failed");
        return false;
    }
    Serial.printf("Audio ready: %u samples + %u preroll, %u bytes PSRAM\n",
                  (unsigned)s_pcmCapacity, (unsigned)PREROLL_SAMPLES,
                  (unsigned)((s_pcmCapacity + PREROLL_SAMPLES) * 2));
    return true;
}

static int16_t readSample() {
    return (int16_t)I2S.read();
}

void waitForVoice() {
    waitForVoiceTimeout(0);  // 0 = block forever
}

bool waitForVoiceTimeout(uint32_t timeoutMs) {
    Serial.printf("Listening for wake sound%s...\n",
                  timeoutMs ? " (timed)" : "");
    const int WINDOW       = 320;
    const int LOUD_NEEDED  = 60;
    int loudCount = 0;
    int idx = 0;
    int32_t peak = 0;

    s_prerollWrite = 0;
    s_prerollFull  = false;
    s_prerollCount = 0;

    uint32_t started = millis();
    while (true) {
        if (timeoutMs && (millis() - started) > timeoutMs) {
            return false;
        }

        int16_t s = readSample();

        s_preroll[s_prerollWrite] = s;
        s_prerollWrite++;
        if (s_prerollWrite >= PREROLL_SAMPLES) {
            s_prerollWrite = 0;
            s_prerollFull = true;
        }

        int32_t a = abs((int32_t)s);
        if (a > VAD_THRESHOLD) {
            loudCount++;
            if (a > peak) peak = a;
        }
        idx++;
        if (idx >= WINDOW) {
            if (loudCount >= LOUD_NEEDED) {
                Serial.printf("Voice detected (peak=%d, loud=%d/%d)\n",
                              (int)peak, loudCount, WINDOW);
                size_t available = s_prerollFull ? PREROLL_SAMPLES : s_prerollWrite;
                size_t start = s_prerollFull ? s_prerollWrite : 0;
                for (size_t i = 0; i < available; ++i) {
                    s_pcm[i] = s_preroll[(start + i) % PREROLL_SAMPLES];
                }
                s_prerollCount = available;
                Serial.printf("Preroll: %u samples (~%u ms) prepended\n",
                              (unsigned)available,
                              (unsigned)(available * 1000 / SAMPLE_RATE));
                return true;
            }
            idx = 0;
            loudCount = 0;
            peak = 0;
            yield();  // Alimentar al watchdog entre ventanas.
        }
    }
}

static void writeWavHeader(uint8_t* buf, uint32_t pcmBytes) {
    uint32_t chunkSize  = 36 + pcmBytes;
    uint32_t byteRate   = SAMPLE_RATE * 2;
    uint16_t blockAlign = 2;

    memcpy(buf + 0,  "RIFF", 4);
    memcpy(buf + 4,  &chunkSize, 4);
    memcpy(buf + 8,  "WAVE", 4);
    memcpy(buf + 12, "fmt ", 4);
    uint32_t sub1 = 16;          memcpy(buf + 16, &sub1, 4);
    uint16_t fmt  = 1;           memcpy(buf + 20, &fmt, 2);
    uint16_t ch   = 1;           memcpy(buf + 22, &ch, 2);
    uint32_t sr   = SAMPLE_RATE; memcpy(buf + 24, &sr, 4);
                                 memcpy(buf + 28, &byteRate, 4);
                                 memcpy(buf + 32, &blockAlign, 2);
    uint16_t bps  = 16;          memcpy(buf + 34, &bps, 2);
    memcpy(buf + 36, "data", 4);
    memcpy(buf + 40, &pcmBytes, 4);
}

uint8_t* recordWav(size_t& outSize) {
    Serial.println("Recording...");
    uint32_t started  = millis();
    uint32_t lastLoud = millis();
    // Start AFTER the preroll samples that waitForVoice already wrote.
    size_t   idx = s_prerollCount;
    uint64_t energySum = 0;   // sum of |sample| for RMS-ish check

    // Account for energy of the preroll so the avgAmp check is fair.
    for (size_t i = 0; i < s_prerollCount; ++i) {
        energySum += (uint32_t)abs((int32_t)s_pcm[i]);
    }

    while (idx < s_pcmCapacity) {
        int16_t s = readSample();
        s_pcm[idx++] = s;
        int32_t a = abs((int32_t)s);
        energySum += (uint32_t)a;

        if (a > VAD_THRESHOLD) {
            lastLoud = millis();
        }
        if (millis() - started > 500 &&
            millis() - lastLoud > SILENCE_TIMEOUT_MS) {
            break;
        }
    }

    uint32_t pcmBytes = (uint32_t)(idx * sizeof(int16_t));
    uint32_t avgAmp = idx ? (uint32_t)(energySum / idx) : 0;

    // Reject too-short recordings (< 0.5 s) or low-energy noise:
    // Whisper hallucinates "Thank you" / "Thanks for watching" on silence.
    if (idx < (size_t)(SAMPLE_RATE / 2) || avgAmp < 300) {
        Serial.printf("Discarded recording: %u samples, avg amp=%u\n",
                      (unsigned)idx, (unsigned)avgAmp);
        outSize = 0;
        return nullptr;
    }

    // ---- Software gain: PDM mic on XIAO is quiet. Boost ~6x with clipping. ----
    const int GAIN = 6;
    for (size_t i = 0; i < idx; ++i) {
        int32_t v = (int32_t)s_pcm[i] * GAIN;
        if (v > 32767)  v = 32767;
        if (v < -32768) v = -32768;
        s_pcm[i] = (int16_t)v;
    }

    size_t total = 44 + pcmBytes;
    uint8_t* wav = (uint8_t*)ps_malloc(total);
    if (!wav) {
        Serial.println("[ERR] ps_malloc failed for WAV");
        outSize = 0;
        return nullptr;
    }
    writeWavHeader(wav, pcmBytes);
    memcpy(wav + 44, s_pcm, pcmBytes);
    outSize = total;

    Serial.printf("Recorded %u samples (%u bytes WAV, avg amp=%u, gain x%d)\n",
                  (unsigned)idx, (unsigned)total, (unsigned)avgAmp, GAIN);
    return wav;
}

} // namespace audio
