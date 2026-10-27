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
String session, controlID, permission, preparedControl;
uint32_t preparedSeq=0, appliedSeq=0, permissionUntil=0, lastStatus=0;
bool socketUp=false, stateDirty=true, networkStarted=false;
char serialLine[48];
uint8_t serialLength=0;
bool serialOverflow=false;
uint32_t lastSerialByte=0;

void registro(uint8_t data, uint8_t clock, uint8_t latch, uint8_t value) {
  digitalWrite(latch, LOW); shiftOut(data, clock, MSBFIRST, value); digitalWrite(latch, HIGH);
}
void outputs(uint8_t code) {
  registro(DATOS_1,RELOJ_1,LATCH_1,0);
  registro(DATOS_2,RELOJ_2,LATCH_2,0);
  if(code>=1 && code<=8) registro(DATOS_1,RELOJ_1,LATCH_1,1U<<(code-1));
  else if(code>=9 && code<=13) registro(DATOS_2,RELOJ_2,LATCH_2,1U<<(code-9));
  stateDirty=true;
}
ControlCore core(outputs);

void tickCore(uint32_t now) {
  const bool powerPulse=core.pulse && core.code==9;
  core.tick(now);
  if(powerPulse && !core.pulse && core.powerKnown && strcmp(core.reason,"pulso_finalizado")==0)
    Serial.println(core.power?F("Carro marcado como encendido."):F("Carro marcado como apagado."));
}

void addState(JsonDocument& doc, const char* type) {
  doc["tipo"]=type; doc["sesion"]=session;
  doc["modo"]=core.remoteMode?"wifi":"serial";
  doc["codigo"]=core.code;
  if(core.powerKnown) doc["encendido_estimado"]=core.power;
  else doc["encendido_estimado"]=nullptr;
  doc["motivo"]=core.reason;
}
void sendDocument(JsonDocument& doc) {
  if(!socketUp || session.length()==0) return;
  String text; serializeJson(doc,text); socketAPI.sendTXT(text);
}
void reportState(const char* type="estado") {
  JsonDocument doc; addState(doc,type); sendDocument(doc);
  stateDirty=false; lastStatus=millis();
}
void acknowledge(uint32_t seq, bool ok, uint32_t duration=0, const char* error="") {
  JsonDocument doc; addState(doc,"ack"); doc["seq"]=seq;
  doc["ok"]=ok; doc["duracion_ms"]=duration;
  if(!ok)doc["motivo"]=error;
  sendDocument(doc);
}
void clearPermission() { permission=""; preparedControl=""; preparedSeq=0; }
void receiveOrder(uint8_t* data, size_t length) {
  if(length>768) return;
  JsonDocument doc;
  if(deserializeJson(doc,data,length,DeserializationOption::NestingLimit(3)))return;
  const String type=doc["tipo"]|"";
  const String receivedSession=doc["sesion"]|"";
  const uint32_t now=millis();
  tickCore(now);
  if(type=="saludo") {
    if(receivedSession.length()!=16)return;
    session=receivedSession; appliedSeq=0; controlID=""; clearPermission();
    if(core.remoteMode)core.resetRemote();
    reportState("listo"); return;
  }
  if(session.length()==0 || receivedSession!=session)return;
  if(type=="latido") {
    const String id=doc["control"]|"";
    const uint32_t ttl=doc["ttl_ms"]|0;
    if(id==controlID && id.length()==32 && ttl>=100 && ttl<=800)core.renew(now,ttl);
    return;
  }
  if(!doc["seq"].is<uint32_t>())return;
  const uint32_t seq=doc["seq"].as<uint32_t>();
  if(seq==0 || seq<=appliedSeq){acknowledge(seq,false,0,"secuencia_antigua");return;}
  if(type=="parar") {
    appliedSeq=seq; clearPermission();controlID="";
    core.resetRemote(); acknowledge(seq,true);return;
  }
  if(type=="preparar") {
    const String id=doc["control"]|"";
    if(!core.remoteMode || core.remoteFault || id.length()!=32) {
      JsonDocument response;response["tipo"]="preparado";response["sesion"]=session;response["seq"]=seq;
      response["permiso"]="";sendDocument(response);return;
    }
    preparedSeq=seq;preparedControl=id;
    permission=String(ESP.random(),HEX)+String(ESP.random(),HEX);
    permissionUntil=now+500;
    JsonDocument response;response["tipo"]="preparado";response["sesion"]=session;
    response["seq"]=seq;response["permiso"]=permission;sendDocument(response);return;
  }
  if(type=="orden") {
    const String id=doc["control"]|"", suppliedPermission=doc["permiso"]|"";
    if(seq!=preparedSeq || id!=preparedControl || permission.length()==0 || suppliedPermission!=permission ||
       ControlCore::expired(now,permissionUntil)) {
      clearPermission();acknowledge(seq,false,0,"permiso_vencido");return;
    }
    clearPermission();
    if(!doc["codigo"].is<uint8_t>() || !doc["ttl_ms"].is<uint32_t>()) {
      acknowledge(seq,false,0,"orden_invalida");return;
    }
    const uint8_t code=doc["codigo"].as<uint8_t>();
    const uint32_t ttl=doc["ttl_ms"].as<uint32_t>(), duration=core.duration(code);
    if(!core.apply(code,true,now,ttl)){acknowledge(seq,false,0,"modo_pulso_o_estado_no_disponible");return;}
    appliedSeq=seq;controlID=id;
    acknowledge(seq,true,duration);
  }
}
void socketEvent(WStype_t type, uint8_t* payload, size_t length) {
  if(type==WStype_CONNECTED) {
    socketUp=true; session=""; controlID=""; clearPermission();
    Serial.println(F("Canal API conectado; esperando saludo."));
  } else if(type==WStype_TEXT) receiveOrder(payload,length);
  else if(type==WStype_DISCONNECTED) {
    socketUp=false;session="";controlID="";clearPermission();core.lost();
    Serial.println(F("Canal API desconectado."));
  }
}
void serialCommand() {
  serialLine[serialLength]='\0';
  if(serialOverflow){Serial.println(F("Entrada serial demasiado larga; descartada."));return;}
  String line=serialLine;line.trim();line.toUpperCase();
  if(line.length()==0)return;
  if(line=="SERIAL") {core.mode(false);controlID="";clearPermission();Serial.println(F("Modo SERIAL."));return;}
  if(line=="WIFI") {core.mode(true);controlID="";clearPermission();Serial.println(F("Modo WIFI; salidas liberadas."));reportState("listo");return;}
  if(line=="ENCENDIDO 0" || line=="ENCENDIDO 1") {
    if(core.code!=0){Serial.println(F("Envia 0 antes de corregir el estado supuesto."));return;}
    core.power=line.endsWith("1");core.powerKnown=true;stateDirty=true;
    Serial.println(core.power?F("Carro marcado como encendido."):F("Carro marcado como apagado."));return;
  }
  if(line=="ESTADO") {
    Serial.printf("Modo: %s | salida: %u | WiFi: %s | API: %s\n",core.remoteMode?"WIFI":"SERIAL",core.code,
                  WiFi.status()==WL_CONNECTED?"conectado":"sin red",socketUp?"conectada":"sin canal");return;
  }
  for(size_t i=0;i<line.length();++i)if(!isDigit(line[i])) {Serial.println(F("Usa 0-13, SERIAL, WIFI, ESTADO o ENCENDIDO 0/1."));return;}
  if(line.length()>2 || line.toInt()>13){Serial.println(F("Comando invalido: usa 0 a 13."));return;}
  const uint8_t code=line.toInt();
  // Una orden local toma el control aunque interrumpa un pulso remoto.
  if(code!=0 && core.remoteMode){core.mode(false);controlID="";clearPermission();}
  if(core.apply(code,false,millis()))Serial.printf("Comando serial: %u\n",code);
  else Serial.println(F("Pulso en curso o encendido supuesto sin determinar; envia 0 para liberar."));
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
  WiFi.persistent(false);WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);
  if(String(WIFI_SSID)!="TU_RED_WIFI")WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  socketAPI.onEvent(socketEvent);
  Serial.println(F("Control listo a 9600 baudios. Numeros 0-13, SERIAL, WIFI, ESTADO."));
}
void loop() {
  readSerial();tickCore(millis());
  if(WiFi.status()!=WL_CONNECTED)core.lost();
  if(!networkStarted && WiFi.status()==WL_CONNECTED && String(API_HOST)!="IP_O_HOST_DE_EC2") {
    // Iniciar una sola vez. ESPAsyncTCP se encarga de reconectar sin esperar TCP.
    const String path="/dispositivo/ws/vehiculos/"+String(VEHICLE_ID);
    socketAPI.begin(API_HOST,API_PORT,path.c_str(),"");
    socketAPI.setAuthorization((String("Bearer ")+DEVICE_TOKEN).c_str());
    networkStarted=true;
  }
  // En modo async no se llama socketAPI.loop(): los callbacks reciben los datos.
  if(socketUp && session.length()>0 && (stateDirty || millis()-lastStatus>=400))reportState();
  yield();
}
