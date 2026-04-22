#include "wifi_manager.h"
#include "config.h"

#include <WiFi.h>

namespace wifi_mgr {

bool connect() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.printf("Connecting to WiFi: %s\n", WIFI_SSID);

    uint32_t deadline = millis() + 20000;
    while (WiFi.status() != WL_CONNECTED && millis() < deadline) {
        delay(300);
        Serial.print('.');
    }
    Serial.println();

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[ERR] WiFi FAILED");
        return false;
    }
    Serial.printf("WiFi OK, IP=%s, RSSI=%d\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());

    // Override router DNS (DIGI sometimes returns 0.0.0.0 for CDN hosts).
    // Keep current IP/gateway/subnet, force Cloudflare + Google DNS.
    IPAddress dns1(1, 1, 1, 1);
    IPAddress dns2(8, 8, 8, 8);
    WiFi.config(WiFi.localIP(), WiFi.gatewayIP(), WiFi.subnetMask(), dns1, dns2);
    Serial.printf("DNS set to %s, %s\n", dns1.toString().c_str(), dns2.toString().c_str());

    // NTP: Europa/Madrid (CET/CEST automatico). Usado por brain_context.
    configTzTime("CET-1CEST,M3.5.0,M10.5.0/3",
                 "pool.ntp.org", "time.google.com");

    return true;
}

bool ensureConnected() {
    if (WiFi.status() == WL_CONNECTED) return true;
    Serial.println("[WARN] WiFi dropped, reconnecting...");
    return connect();
}

} // namespace wifi_mgr
