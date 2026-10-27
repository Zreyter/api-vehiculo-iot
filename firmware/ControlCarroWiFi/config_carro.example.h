#pragma once
// Copia este archivo como config_carro.h y completa estos valores personalmente.
// La red debe ser de 2.4 GHz. No pongas credenciales de RDS en el ESP8266.
static const char WIFI_SSID[] = "TU_RED_WIFI";
static const char WIFI_PASSWORD[] = "TU_PASSWORD_WIFI";
static const char API_HOST[] = "IP_O_HOST_DE_EC2";  // sin http:// ni ruta
static const uint16_t API_PORT = 8000;
static const uint32_t VEHICLE_ID = 1;
// DEVICE_TOKEN de la API; si no existe, se utiliza CONTROL_TOKEN.
static const char DEVICE_TOKEN[] = "TU_TOKEN";
static const bool START_IN_WIFI = true;
