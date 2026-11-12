#!/usr/bin/env bash
set -euo pipefail

archive=${1:?Falta el paquete de la API}
rds_host=${2:?Falta el endpoint de RDS}
if [[ $(id -u) != 0 || ! -f $archive || ! $rds_host =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]]; then
    echo 'Ejecuta el instalador con sudo, un paquete válido y el endpoint de RDS.' >&2
    exit 1
fi

service=vehiculo-iot
base=/opt/vehiculo-iot
config=/etc/vehiculo-iot
env_file=$config/api.env
unit=/etc/systemd/system/$service.service
exec 9>/run/lock/vehiculo-iot-install.lock
if ! flock -n 9; then
    echo 'Ya hay una instalación en curso.' >&2
    exit 1
fi
if [[ -e $unit && ! -L $base/current ]]; then
    echo "Ya existe $unit sin un despliegue administrado. Revisa ese servicio antes de continuar." >&2
    exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv ca-certificates curl
if ! id "$service" >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$base" --shell /usr/sbin/nologin "$service"
fi
install -d -m 0755 "$base" "$base/releases"
install -d -m 0750 -o root -g "$service" "$config"

# El entorno virtual se crea en su ubicación final para conservar sus rutas.
release=$(mktemp -d "$base/releases/release.XXXXXXXX")
chmod 0755 "$release"
tar --no-same-owner --no-same-permissions -xzf "$archive" -C "$release"
python3 -m venv "$release/.venv"
"$release/.venv/bin/python" -m pip install --disable-pip-version-check -r "$release/requirements.txt"

if [[ ! -s $config/rds-ca.pem ]]; then
    ca_download=$(mktemp "$config/ca.XXXXXXXX")
    curl --fail --silent --show-error --retry 2 --max-time 30 \
        https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem -o "$ca_download"
    chmod 0644 "$ca_download"
    mv -f -- "$ca_download" "$config/rds-ca.pem"
fi

if [[ ! -e $env_file ]]; then
    python3 - "$env_file" "$rds_host" "$service" "$config/rds-ca.pem" <<'PY'
import getpass
import grp
import os
import secrets
import string
import sys

path, host, group, ca = sys.argv[1:]
with open('/dev/tty', encoding='utf-8') as terminal:
    print(f'Endpoint RDS: {host}', flush=True)
    print('Usuario MySQL [admin]: ', end='', flush=True)
    user = terminal.readline().strip() or 'admin'
    password = getpass.getpass('Contraseña MySQL (Enter para dejarla pendiente): ')
    device_token = getpass.getpass('DEVICE_TOKEN anterior (Enter para generar uno): ')
    print('Origen HTTPS del frontend (Enter si aún no está publicado): ', end='', flush=True)
    origin = terminal.readline().strip()

if origin:
    from urllib.parse import urlsplit
    url = urlsplit(origin)
    if (url.scheme != 'https' or not url.hostname or url.path or url.query
            or url.fragment or url.username or url.password or any(c.isspace() for c in origin)):
        raise SystemExit('Escribe el origen exacto, por ejemplo https://excavadora.vercel.app')

import json
alphabet = string.ascii_letters + string.digits
values = {
    'MYSQL_HOST': host, 'MYSQL_PORT': '3306', 'MYSQL_USER': user,
    'MYSQL_PASSWORD': password, 'MYSQL_DATABASE': 'vehiculo_iot', 'MYSQL_SSL_CA': ca,
    'CONTROL_TOKEN': ''.join(secrets.choice(alphabet) for _ in range(8)),
    'DEVICE_TOKEN': device_token or secrets.token_urlsafe(32), 'BROWSER_ORIGINS': json.dumps([origin] if origin else []),
}

def environment_value(value):
    if any(c in value for c in ('\n', '\r', '\0')):
        raise SystemExit('La configuración debe contener un valor por línea.')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'

content = ''.join(f'{key}={environment_value(value)}\n' for key, value in values.items())
with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o640), 'w', encoding='utf-8') as stream:
    os.fchown(stream.fileno(), 0, grp.getgrnam(group).gr_gid)
    stream.write(content)
PY
fi

(
    cd "$release"
    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -c 'from app.main import app; print("FastAPI", app.version)'
)

cat > "$unit" <<'UNIT'
[Unit]
Description=API FastAPI de la excavadora IoT
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=vehiculo-iot
Group=vehiculo-iot
WorkingDirectory=/opt/vehiculo-iot/current
EnvironmentFile=/etc/vehiculo-iot/api.env
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/vehiculo-iot/current/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
UNIT

previous=$(readlink "$base/current" || true)
ln -s -- "$release" "$release/current-link"
mv -Tf -- "$release/current-link" "$base/current"
systemctl daemon-reload

ready=0
if systemd-analyze verify "$unit" && systemctl restart "$service"; then
    for attempt in {1..15}; do
        if systemctl is-active --quiet "$service" &&
            curl -fs --max-time 2 http://127.0.0.1:8000/openapi.json -o /dev/null; then
            ready=1
            break
        fi
        sleep 1
    done
fi

if (( ! ready )); then
    journalctl -u "$service" -n 25 --no-pager >&2
    if [[ -n $previous ]]; then
        ln -s -- "$previous" "$release/current-link"
        mv -Tf -- "$release/current-link" "$base/current"
        systemctl restart "$service"
    fi
    exit 1
fi

systemctl enable "$service"
printf 'Servicio activo: '; systemctl is-active "$service"
printf 'Arranque automático: '; systemctl is-enabled "$service"
printf 'Swagger HTTP: '; curl -fsS --max-time 5 -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/docs
printf 'Lectura del historial de RDS (HTTP): '
curl -sS --max-time 15 -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8000/vehiculos/1/historial?limite=1'
echo 'Credenciales guardadas en /etc/vehiculo-iot/api.env.'
