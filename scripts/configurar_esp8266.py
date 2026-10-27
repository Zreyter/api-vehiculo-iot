"""Genera config_carro.h local sin mostrar secretos ni modificar .env."""
import getpass
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def configured_token():
    path = ROOT / '.env'
    values = {}
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            match = re.match(r'^\s*(DEVICE_TOKEN|CONTROL_TOKEN)\s*=\s*(.*?)\s*$', line)
            if match:
                value = match[2]
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                else:
                    value = value.split(' #', 1)[0].strip()
                values[match[1]] = value
    return values.get('DEVICE_TOKEN') or values.get('CONTROL_TOKEN') or ''


def main():
    destination = ROOT / 'firmware/ControlCarroWiFi/config_carro.h'
    if destination.exists():
        raise SystemExit('config_carro.h ya existe. Edítalo directamente para conservar tus valores.')
    ssid = input('Nombre de la red WiFi de 2.4 GHz: ').strip()
    password = getpass.getpass('Contraseña WiFi (no se muestra): ')
    host = input('IP o nombre de EC2, sin http:// ni ruta: ').strip()
    port = int(input('Puerto de la API [8000]: ').strip() or '8000')
    vehicle = int(input('ID del vehículo [1]: ').strip() or '1')
    token = configured_token()
    if not token:
        token = getpass.getpass('CONTROL_TOKEN o DEVICE_TOKEN de EC2 (no se muestra): ').strip()
    if not ssid or not re.fullmatch(r'[A-Za-z0-9.-]+', host) or not 1 <= port <= 65535 or vehicle <= 0 or not token or any(ord(c)<32 for c in token):
        raise SystemExit('Hay datos inválidos. No se escribió la configuración.')
    literal = lambda value: json.dumps(value, ensure_ascii=True)
    content = '\n'.join([
        '#pragma once', '// Configuración privada; excluida de Git.',
        f'static const char WIFI_SSID[] = {literal(ssid)};',
        f'static const char WIFI_PASSWORD[] = {literal(password)};',
        f'static const char API_HOST[] = {literal(host)};',
        f'static const uint16_t API_PORT = {port};',
        f'static const uint32_t VEHICLE_ID = {vehicle};',
        f'static const char DEVICE_TOKEN[] = {literal(token)};',
        'static const bool START_IN_WIFI = true;', '',
    ])
    with destination.open('x', encoding='utf-8') as stream:
        stream.write(content)
    print('Configuración creada en firmware/ControlCarroWiFi/config_carro.h. No se modificó .env.')


if __name__ == '__main__':
    main()
