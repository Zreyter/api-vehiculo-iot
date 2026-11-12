#include <ESP8266WiFi.h>
#include <ESPAsyncTCP.h>
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
char serialLine[48];
uint8_t serialLength=0;
bool serialOverflow=false;
uint32_t lastSerialByte=0;
uint32_t sentFrames=0, failedFrames=0, receivedFrames=0;

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
void serialCommand() {
  serialLine[serialLength]='\0';
  if(serialOverflow){Serial.println(F("Entrada serial demasiado larga; descartada."));return;}
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
    Serial.printf("RSSI=%d dBm | heap=%u | tiempo_ms=%lu\n",WiFi.RSSI(),ESP.getFreeHeap(),millis());
    Serial.printf("TX=%lu | TX_fallidos=%lu | RX=%lu | edad_estado_ms=%lu\n",sentFrames,failedFrames,receivedFrames,millis()-lastStatus);return;
  }
  for(size_t i=0;i<line.length();++i)if(!isDigit(line[i])) {Serial.println(F("Usa 0-13, SERIAL, WIFI, ESTADO o ENCENDER o APAGAR."));return;}
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
      serialCommand();serialLength=0;serialOverflow=false;
    } else if(serialLength<sizeof(serialLine)-1)serialLine[serialLength++]=c;
    else serialOverflow=true;
  }
  // Una línea parcial no se ejecuta sola ni mantiene ocupado el bucle.
  if((serialLength||serialOverflow) && millis()-lastSerialByte>1000) {serialLength=0;serialOverflow=false;}
}
void setup() {
  Serial.begin(9600);
  for(uint8_t pin : {DATOS_1,RELOJ_1,LATCH_1,DATOS_2,RELOJ_2,LATCH_2}){pinMode(pin,OUTPUT);digitalWrite(pin,LOW);}
  core.mode(START_IN_WIFI);
  WiFi.persistent(false);WiFi.mode(WIFI_STA);WiFi.setSleepMode(WIFI_NONE_SLEEP);WiFi.setAutoReconnect(true);
  if(String(WIFI_SSID)!="TU_RED_WIFI")WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  socketAPI.onEvent(socketEvent);
  Serial.println(F("Control listo a 9600 baudios. Numeros 0-13, SERIAL, WIFI, ESTADO."));
}
void loop() {
  readSerial();tickCore(millis());
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
