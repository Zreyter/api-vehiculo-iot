#pragma once
#include <stdint.h>

// Sin dependencias de red: toda salida pasa por esta máquina de estados.
class ControlCore {
public:
  using Output = void (*)(uint8_t);
  Output writeOutput;
  uint8_t code = 0;
  bool remoteMode = true;
  bool pulse = false, remoteFault = false;
  bool timedDemo = false;
  uint32_t demoUntil = 0;
  uint32_t pulseUntil = 0, remoteUntil = 0;
  const char* reason = "inicio";

  explicit ControlCore(Output output) : writeOutput(output) {}
  static bool expired(uint32_t now, uint32_t deadline) {
    return static_cast<int32_t>(now - deadline) >= 0;
  }
  void stop(const char* why) {
    code = 0; pulse = false; timedDemo = false; reason = why;
    writeOutput(0);
  }
  void mode(bool wifi) {
    stop(wifi ? "modo_wifi" : "modo_serial");
    remoteMode = wifi; remoteFault = false;
  }
  void resetRemote() { stop("parada_remota"); remoteFault = false; }
  void lost() {
    if (remoteMode && !remoteFault) { stop("conexion_perdida"); remoteFault = true; }
  }
  void renew(uint32_t now, uint32_t ttl) {
    if (remoteMode && !remoteFault && code != 0) remoteUntil = now + ttl;
  }
  uint32_t duration(uint8_t requested) const {
    return requested == 9 ? 200 : requested >= 5 && requested <= 8 ? 200 : 0;
  }
  bool apply(uint8_t requested, bool fromWifi, uint32_t now, uint32_t ttl = 800, uint32_t powerMs = 200) {
    if (requested > 13) return false;
    if (requested == 0) { stop("liberado"); return true; }
    if (fromWifi && (!remoteMode || remoteFault || ttl < 100 || ttl > 800)) return false;
    if (pulse || (requested == 9 && powerMs != 200 && powerMs != 2000)) return false;
    if (!fromWifi && remoteMode) mode(false);  // Prioridad del puerto serial.
    timedDemo = false;
    code = requested;
    const uint32_t ms = requested == 9 ? powerMs : duration(requested);
    pulse = ms != 0; pulseUntil = now + ms;
    remoteUntil = now + ttl;
    reason = fromWifi ? "orden_wifi" : "orden_serial";
    writeOutput(requested);
    return true;
  }
  bool applyDemo(uint8_t requested, uint32_t now, uint32_t ttl, uint32_t duration) {
    if (!((requested >= 1 && requested <= 4) || (requested >= 10 && requested <= 13))
        || duration == 0 || duration > 60000) return false;
    if (!apply(requested, true, now, ttl)) return false;
    timedDemo = true; demoUntil = now + duration;
    return true;
  }
  void tick(uint32_t now) {
    // El watchdog tiene prioridad sobre cualquier pulso en curso.
    if (remoteMode && code != 0 && expired(now, remoteUntil)) {
      stop("watchdog"); remoteFault = true; return;
    }
    if (timedDemo && expired(now, demoUntil)) {
      stop("paso_demo_finalizado"); return;
    }
    if (pulse && expired(now, pulseUntil)) {
      pulse = false; code = 0; reason = "pulso_finalizado";
      writeOutput(0);
    }
  }
};
