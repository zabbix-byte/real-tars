// Mini sketch: escanea y lista todas las redes WiFi visibles.
// Sube este sketch, abre Serial Monitor a 115200 y mira qué redes aparecen.

#include <WiFi.h>

void setup() {
    Serial.begin(115200);
    delay(1500);
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    delay(100);
    Serial.println("\nWiFi scanner ready.");
}

void loop() {
    Serial.println("\nScanning...");
    int n = WiFi.scanNetworks();
    if (n == 0) {
        Serial.println("No networks found.");
    } else {
        Serial.printf("%d networks found:\n", n);
        Serial.println("  #  RSSI  CH  ENC  SSID");
        for (int i = 0; i < n; i++) {
            Serial.printf("  %2d  %4d  %2d  %3d  %s\n",
                i + 1,
                WiFi.RSSI(i),
                WiFi.channel(i),
                WiFi.encryptionType(i),
                WiFi.SSID(i).c_str());
        }
    }
    WiFi.scanDelete();
    delay(5000);
}
