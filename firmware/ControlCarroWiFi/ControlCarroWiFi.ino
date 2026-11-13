#include <ESP8266WiFi.h>
#include <ESPAsyncTCP.h>
#include <LittleFS.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include "ControlCore.h"
#if __has_include("config_carro.h")
#include "config_carro.h"
#else
#include "config_carro.example.h"
#endif

static_assert(WEBSOCKETS_NETWORK_TYPE == NETWORK_ESP8266_ASYNC,
              "Conserva ControlCarroWiFi.ino.globals.h en la carpeta del sketch.");
const uint8_t DATOS_1=13, RELOJ_1=14, LATCH_1=12;
const uint8_t DATOS_2=4, RELOJ_2=5, LATCH_2=16;
WebSocketsClient socketAPI;
String controlID;
uint32_t appliedSeq=0, lastStatus=0;
bool socketUp=false, networkStarted=false;
// Hasta seis caracteres JSON por byte de SSID o clave (32 + 64 bytes).
char serialLine[640];
uint16_t serialLength=0;
bool serialOverflow=false;
uint32_t lastSerialByte=0;
uint32_t sentFrames=0, failedFrames=0, receivedFrames=0;

struct WifiCredentials {
  char ssid[33];
  char password[65];
};
const char WIFI_PROFILE[] = "/wifi-serial.dat";
const char WIFI_PROFILE_TEMP[] = "/wifi-serial.tmp";
constexpr uint32_t WIFI_TRIAL_MS = 20000;
WifiCredentials savedWifi{}, trialWifi{};
bool wifiStorageReady = false, wifiTrial = false;
uint32_t wifiTrialStarted = 0;

void registro(uint8_t data, uint8_t clock, uint8_t latch, uint8_t value) {
  digitalWrite(latch, LOW); shiftOut(data, clock, MSBFIRST, value); digitalWrite(latch, HIGH);
}
void outputs(uint8_t code) {
  registro(DATOS_1,RELOJ_1,LATCH_1,0);
  registro(DATOS_2,RELOJ_2,LATCH_2,0);
  if(code>=1 && code<=8) registro(DATOS_1,RELOJ_1,LATCH_1,1U<<(code-1));
  else if(code>=9 && code<=13) registro(DATOS_2,RELOJ_2,LATCH_2,1U<<(code-9));
}
ControlCore core(outputs);

void tickCore(uint32_t now) { core.tick(now); }

void reportState() {
  if(!socketUp) return;
  JsonDocument doc;
  doc["tipo"]="estado";
  doc["modo"]=core.remoteMode?"wifi":"serial";
  doc["codigo"]=core.code;
  doc["motivo"]=core.reason;
  if(controlID.length()) doc["control"]=controlID;
  String text; serializeJson(doc,text);
  if(socketAPI.sendTXT(text))sentFrames++;else failedFrames++;
  lastStatus=millis();
}
void setMode(bool wifi) {
  core.mode(wifi);
  controlID="";
  if(wifi && socketUp) core.remoteFault=true; // La próxima sesión envía parar antes de mover.
  reportState();
}
void receiveOrder(uint8_t* data, size_t length) {
  receivedFrames++;
  if(!socketUp || length>768) return;
  JsonDocument doc;
  if(deserializeJson(doc,data,length,DeserializationOption::NestingLimit(3)))return;
  const String type=doc["tipo"]|"";
  const uint32_t now=millis();
  tickCore(now);
  if(type=="latido") {
    const String id=doc["control"]|"";
    const uint32_t ttl=doc["ttl_ms"]|0U;
    if(id==controlID && id.length()==32 && ttl>=100 && ttl<=800)core.renew(now,ttl);
    return;
  }
  if((type!="orden" && type!="parar") || !doc["seq"].is<uint32_t>())return;
  const uint32_t seq=doc["seq"].as<uint32_t>();
  if(seq<=appliedSeq)return;
  appliedSeq=seq;
  if(!core.remoteMode)return;
  if(type=="parar") {
    controlID="";
    core.resetRemote();
    return;
  }
  const String id=doc["control"]|"";
  if(id.length()!=32 || !doc["codigo"].is<uint8_t>() || !doc["ttl_ms"].is<uint32_t>()) return;
  if(controlID.length() && controlID!=id) return;
  const uint8_t code=doc["codigo"].as<uint8_t>();
  const uint32_t ttl=doc["ttl_ms"].as<uint32_t>();
  if(code==0 || ttl<100 || ttl>800) return;
  uint32_t duration=core.duration(code);
  if(code==9) {
    if(!doc["pulso_ms"].is<uint32_t>()) return;
    duration=doc["pulso_ms"].as<uint32_t>();
    if(duration!=200 && duration!=2000) return;
  } else if(!doc["pulso_ms"].isNull()) return;
  bool applied;
  if(!doc["demo_ms"].isNull()) {
    if(!doc["demo_ms"].is<uint32_t>()) return;
    applied=core.applyDemo(code,now,ttl,doc["demo_ms"].as<uint32_t>());
  } else {
    applied=core.apply(code,true,now,ttl,duration);
  }
  if(applied) controlID=id;
}
void socketEvent(WStype_t type, uint8_t* payload, size_t length) {
  if (wifiTrial && type != WStype_DISCONNECTED) return;
  if(type==WStype_CONNECTED) {
    socketUp=true; controlID=""; appliedSeq=0; lastStatus=millis();
    if(core.remoteMode)core.resetRemote();
    Serial.printf("[%lu] WebSocket directo conectado. RSSI=%d heap=%u\n",millis(),WiFi.RSSI(),ESP.getFreeHeap());
  } else if(type==WStype_TEXT) receiveOrder(payload,length);
  else if(type==WStype_DISCONNECTED) {
    socketUp=false;controlID="";core.lost();
    Serial.printf("[%lu] API desconectada. WiFi=%d RSSI=%d heap=%u motivo=%.*s\n",millis(),WiFi.status(),WiFi.RSSI(),ESP.getFreeHeap(),(int)(length>64?64:length),payload?(char*)payload:"");
  }
}
bool validWifiCredentials(const WifiCredentials& credentials) {
  const size_t ssidLength = strnlen(credentials.ssid, sizeof(credentials.ssid));
  const size_t passwordLength = strnlen(credentials.password, sizeof(credentials.password));
  if (ssidLength == 0 || ssidLength >= sizeof(credentials.ssid)) return false;
  if (passwordLength == 0 || (passwordLength >= 8 && passwordLength <= 63)) return true;
  if (passwordLength != 64) return false;
  for (size_t i = 0; i < passwordLength; ++i) {
    if (!isxdigit(static_cast<unsigned char>(credentials.password[i]))) return false;
  }
  return true;
}

bool readWifiProfile(const char* path, WifiCredentials& credentials) {
  File file = LittleFS.open(path, "r");
  return file && file.size() == sizeof(credentials) &&
         file.read(reinterpret_cast<uint8_t*>(&credentials), sizeof(credentials)) == sizeof(credentials) &&
         validWifiCredentials(credentials);
}

bool saveWifiProfile(const WifiCredentials& credentials) {
  File file = LittleFS.open(WIFI_PROFILE_TEMP, "w");
  if (!file) return false;
  const size_t written = file.write(reinterpret_cast<const uint8_t*>(&credentials), sizeof(credentials));
  file.close();
  WifiCredentials check{};
  const bool saved = written == sizeof(credentials) && readWifiProfile(WIFI_PROFILE_TEMP, check) &&
                     memcmp(&credentials, &check, sizeof(credentials)) == 0 &&
                     LittleFS.rename(WIFI_PROFILE_TEMP, WIFI_PROFILE);
  if (!saved) LittleFS.remove(WIFI_PROFILE_TEMP);
  return saved;
}

void connectConfiguredWifi() {
  if (savedWifi.ssid[0]) WiFi.begin(savedWifi.ssid, savedWifi.password);
  else if (WIFI_SSID[0] && strcmp(WIFI_SSID, "TU_RED_WIFI") != 0) WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void registerWifi(const char* arguments) {
  if (wifiTrial) {
    Serial.println(F("Ya se esta probando una red. Consulta ESTADO."));
    return;
  }
  JsonDocument document;
  const auto error = deserializeJson(document, arguments, DeserializationOption::NestingLimit(1));
  const JsonArrayConst fields = document.as<JsonArrayConst>();
  const JsonString ssid = fields[0].as<JsonString>();
  const JsonString password = fields[1].as<JsonString>();
  WifiCredentials credentials{};
  if (error || fields.size() != 2 || ssid.isNull() || password.isNull() ||
      ssid.size() >= sizeof(credentials.ssid) || password.size() >= sizeof(credentials.password) ||
      memchr(ssid.c_str(), 0, ssid.size()) || memchr(password.c_str(), 0, password.size())) {
    Serial.println(F("Usa WIFI RED [\"Nombre de red\",\"Contrasena\"]"));
    return;
  }
  memcpy(credentials.ssid, ssid.c_str(), ssid.size());
  memcpy(credentials.password, password.c_str(), password.size());
  if (!validWifiCredentials(credentials)) {
    Serial.println(F("SSID: 1-32 bytes. Clave: vacia, 8-63 bytes o 64 digitos hexadecimales."));
    return;
  }
  if (!wifiStorageReady) {
    Serial.println(F("Memoria WiFi no disponible. Se conserva la configuracion anterior."));
    return;
  }

  trialWifi = credentials;
  wifiTrial = true;
  core.lost();  // Libera el control remoto al cerrar su canal.
  socketUp = false;
  controlID = "";
  if (networkStarted) socketAPI.disconnect();
  WiFi.disconnect(false, false);
  WiFi.begin(trialWifi.ssid, trialWifi.password);
  wifiTrialStarted = millis();
  Serial.println(F("Probando la red nueva (hasta 20 segundos)..."));
}

void checkWifiTrial() {
  if (!wifiTrial) return;
  const bool connected = WiFi.status() == WL_CONNECTED && WiFi.SSID() == trialWifi.ssid;
  if (!connected && millis() - wifiTrialStarted < WIFI_TRIAL_MS) return;

  if (networkStarted) socketAPI.disconnect();
  if (connected && saveWifiProfile(trialWifi)) {
    savedWifi = trialWifi;
    Serial.printf("Red guardada y conectada. IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println(connected ? F("No se pudo guardar la red. Volviendo a la configuracion anterior.")
                             : F("No se pudo conectar. Volviendo a la configuracion anterior."));
    WiFi.disconnect(false, true);  // WiFi.persistent(false): solo borra la configuracion temporal.
    connectConfiguredWifi();
  }
  trialWifi = {};
  wifiTrial = false;
}

void serialCommand() {
  serialLine[serialLength]='\0';
  if(serialOverflow){Serial.println(F("Entrada serial invalida o demasiado larga; descartada."));return;}
  const char* input = serialLine + strspn(serialLine, " \t");
  if (strncasecmp(input, "WIFI RED", 8) == 0 &&
      (input[8] == ' ' || input[8] == '\t' || input[8] == '\0')) {
    registerWifi(input + 8);
    return;
  }
  String line=serialLine;line.trim();line.toUpperCase();
  if(line.length()==0)return;
  if(line=="SERIAL") {setMode(false);Serial.println(F("Modo SERIAL."));return;}
  if(line=="WIFI") {setMode(true);Serial.println(F("Modo WIFI; salidas liberadas."));return;}
  if(line=="ENCENDER" || line=="APAGAR") {
    const uint32_t duration=line=="APAGAR"?2000:200;
    if(core.remoteMode){setMode(false);}
    if(core.apply(9,false,millis(),800,duration)) Serial.printf("Pulso enviado al mando: %u ms. Sin confirmar encendido.\n",duration);
    else Serial.println(F("Pulso en curso; envia 0 para liberar."));
    return;
  }
  if(line=="ESTADO") {
    Serial.printf("Modo: %s | salida: %u | WiFi: %s | API: %s\n",core.remoteMode?"WIFI":"SERIAL",core.code,
                  WiFi.status()==WL_CONNECTED?"conectado":"sin red",socketUp?"conectada":"sin canal");
    if (wifiTrial) Serial.println(F("Probando nueva red WiFi."));
    else if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("SSID: %s | IP: %s | Perfil: %s\n", WiFi.SSID().c_str(),
                    WiFi.localIP().toString().c_str(), savedWifi.ssid[0] ? "guardado" : "inicial");
    }
    Serial.printf("RSSI=%d dBm | heap=%u | tiempo_ms=%lu\n",WiFi.RSSI(),ESP.getFreeHeap(),millis());
    Serial.printf("TX=%lu | TX_fallidos=%lu | RX=%lu | edad_estado_ms=%lu\n",sentFrames,failedFrames,receivedFrames,millis()-lastStatus);return;
  }
  for(size_t i=0;i<line.length();++i)if(!isDigit(line[i])) {Serial.println(F("Usa 0-13, SERIAL, WIFI, ESTADO, WIFI RED, ENCENDER o APAGAR."));return;}
  if(line.length()>2 || line.toInt()>13){Serial.println(F("Comando invalido: usa 0 a 13."));return;}
  const uint8_t code=line.toInt();
  // Una orden local toma el control aunque interrumpa un pulso remoto.
  if(code!=0 && core.remoteMode){setMode(false);}
  if(core.apply(code,false,millis()))Serial.printf("Comando serial: %u\n",code);
  else Serial.println(F("Pulso en curso; envia 0 para liberar."));
}
void readSerial() {
  while(Serial.available()) {
    const char c=Serial.read();lastSerialByte=millis();
    if(c=='\r'||c=='\n') {
      serialCommand();memset(serialLine,0,serialLength);serialLength=0;serialOverflow=false;
    } else if(c!='\0' && serialLength<sizeof(serialLine)-1)serialLine[serialLength++]=c;
    else serialOverflow=true;
  }
  // Una línea parcial no se ejecuta sola ni mantiene ocupado el bucle.
  if((serialLength||serialOverflow) && millis()-lastSerialByte>1000) {
    memset(serialLine,0,serialLength);serialLength=0;serialOverflow=false;
  }
}
void setup() {
  Serial.begin(9600);
  for(uint8_t pin : {DATOS_1,RELOJ_1,LATCH_1,DATOS_2,RELOJ_2,LATCH_2}){pinMode(pin,OUTPUT);digitalWrite(pin,LOW);}
  core.mode(START_IN_WIFI);
  WiFi.persistent(false);WiFi.mode(WIFI_STA);WiFi.setSleepMode(WIFI_NONE_SLEEP);WiFi.setAutoReconnect(true);
  wifiStorageReady = LittleFS.begin();
  if (wifiStorageReady && !readWifiProfile(WIFI_PROFILE, savedWifi)) savedWifi = {};
  connectConfiguredWifi();
  socketAPI.onEvent(socketEvent);
  Serial.println(F("Control listo a 9600 baudios. Numeros 0-13, SERIAL, WIFI, ESTADO, WIFI RED."));
}
void loop() {
  readSerial();tickCore(millis());
  checkWifiTrial();
  if (wifiTrial) { yield(); return; }
  // The async transport can close TCP without issuing WStype_DISCONNECTED.
  if(socketUp && !socketAPI.isConnected()) {
    socketUp=false;controlID="";core.lost();
    Serial.printf("[%lu] TCP cerrado; salidas liberadas. RSSI=%d heap=%u\n",millis(),WiFi.RSSI(),ESP.getFreeHeap());
  }
  if(WiFi.status()!=WL_CONNECTED)core.lost();
  if(!networkStarted && WiFi.status()==WL_CONNECTED && String(API_HOST)!="IP_O_HOST_DE_EC2") {
    // Iniciar una sola vez. ESPAsyncTCP se encarga de reconectar sin esperar TCP.
    const String path="/ws/vehiculos/"+String(VEHICLE_ID);
    // En redes distintas, un relay local establece TLS hacia la API.
    socketAPI.begin(API_HOST, API_PORT, path.c_str(), "iot-device-direct");
    socketAPI.setAuthorization((String("Bearer ")+DEVICE_TOKEN).c_str());
    networkStarted=true;
  }
  // Solo despacha reintentos asíncronos; nunca espera una conexión TCP.
  socketAPI.loop();
  if(socketUp && millis()-lastStatus>=400)reportState();
  yield();
}
