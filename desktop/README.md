# Vehículo IoT para Windows

Aplicación portátil para Windows x64 que utiliza el panel de `app/panel` y la misma API FastAPI de EC2. Incluye Conducción por WiFi, teclado y mando, administración, historial, secuencias DEMO y eventos en vivo.

## Descargar

[Descargar Vehículo IoT 1.6 para Windows x64](https://github.com/Zreyter/api-vehiculo-iot/releases/download/v1.6/Vehiculo-IoT-1.6.0-Windows-x64.exe). La [release v1.6](https://github.com/Zreyter/api-vehiculo-iot/releases/tag/v1.6) también incluye instrucciones y checksum SHA256.

## Uso

1. Abre `Vehiculo-IoT-1.6.0-Windows-x64.exe`. No necesita instalar Node.js, Python ni Arduino IDE para ejecutarse.
2. Confirma la dirección vigente de la API; inicialmente propone `http://3.233.212.203:8000`. Puedes cambiarla desde **Aplicación → Cambiar servidor**.
3. Pulsa **Abrir mi panel → Conectar API** e introduce tu `CONTROL_TOKEN` habitual. No hay tokens incorporados en el ejecutable.
4. Para conducir selecciona el vehículo, **Conducción → ESP8266 por WiFi → Activar conducción**. La placa debe estar conectada a la API y en modo WIFI; para cambiar desde serial envía `WIFI` en Termite.
5. Conecta el mando a la computadora donde ejecutas esta aplicación y pulsa un botón para detectarlo. También admite teclado y ratón.

La API de EC2 y el ESP8266 siguen siendo necesarios para conducir por WiFi. El modo **Solo registro en API / RDS** conserva el comportamiento de software del panel. Las secuencias SQL y el botón DEMO del carro son funciones diferentes, igual que en la página web.

El token se mantiene en memoria y se solicita de nuevo al recargar o volver a abrir. La dirección del servidor y las asignaciones del mando/teclado se guardan en `%APPDATA%/vehiculo-iot-desktop/configuracion.json`. No se lee ni modifica `.env`, RDS, certificados o el entorno virtual para configurar la app.

Al perder el foco, minimizar, cambiar de servidor o cerrar se solicita liberar los controles; los temporizadores de la API y el firmware permanecen activos. El serial conserva prioridad. Esta app utiliza WiFi para conducir y no abre COM3.

## Arquitectura

Electron aloja una copia del panel y un adaptador HTTP/WebSocket que escucha exclusivamente en `127.0.0.1`, en un puerto libre. Las peticiones del panel se reenvían al servidor elegido y los WebSocket conservan la autenticación y ajustan el origen esperado por FastAPI.

El documento local permite utilizar Gamepad API aunque el punto de acceso de EC2 sea HTTP. El transporte hacia EC2 conserva el esquema configurado: seleccionar HTTP no cifra ese tramo; HTTPS utiliza la validación normal del certificado. No se desactiva la seguridad web ni se concede acceso a Node.js al panel.

Solo se empaquetan seis archivos públicos del panel, el código de escritorio y los iconos. Las credenciales de MySQL, `.env`, certificados, firmware privado y entornos virtuales quedan fuera del paquete.

## Construir desde el repositorio

Requiere Windows x64 y Node.js 22.12 o posterior con npm. Desde `desktop`:

```powershell
npm ci
npm test
npm run dist
```

El resultado queda en `desktop/dist/Vehiculo-IoT-1.6.0-Windows-x64.exe`. `npm run prepare:panel` copia el panel vigente del repositorio. Las adaptaciones exclusivas del escritorio se aplican a esa copia; no modifican los archivos servidos por FastAPI.

Dependencias fijadas: Electron 45.0.0 y electron-builder 26.15.3. Se incluye `package-lock.json`.

## Verificación

- Ocho pruebas Node del adaptador: configuración, archivos permitidos, HTTP, autenticación, errores, origen y WebSocket.
- Recorridos en Electron con FastAPI real y MySQL/ESP8266 simulados: inicio de sesión, catálogo e historial, eventos, alta administrativa, conducción con renovación, liberación, pulso DEMO, prioridad serial y conservación de preferencias sin guardar el token.
- Verificación de cierre y reapertura, contexto local seguro, disponibilidad de Gamepad API y aislamiento del renderer.

Los recorridos automatizados no envían movimientos al carro real. La prueba del mando físico se realiza conectándolo al equipo del usuario.
