/** Compila el sitio estático. Solo la dirección pública de la API entra al sitio. */
import { cp, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const root = new URL('./', import.meta.url);
const dist = new URL('dist/', root);
const api = new URL(process.env.IOT_API_URL || 'http://127.0.0.1:8000');
const local = ['localhost', '127.0.0.1'].includes(api.hostname);
if (api.username || api.password || api.pathname !== '/' || api.search || api.hash ||
    (api.protocol !== 'https:' && !(local && api.protocol === 'http:')) ||
    (process.env.VERCEL && local)) {
  throw new Error('IOT_API_URL debe ser el origen HTTPS de la API (HTTP solo para pruebas locales).');
}
const vehicleId = Number(process.env.IOT_VEHICLE_ID || 1);
if (!Number.isSafeInteger(vehicleId) || vehicleId < 1) throw new Error('IOT_VEHICLE_ID inválido.');
await mkdir(dist, { recursive: true });
for (const name of ['index.html', 'monitor.html', 'manifest.webmanifest', 'sw.js', 'css', 'js', 'assets']) {
  await cp(new URL(name, root), new URL(name, dist), { recursive: true });
}
await cp(new URL('../app/panel/drive-controller.js', root), new URL('js/drive-controller.js', dist));
await writeFile(new URL('config.js', dist),
  'export default ' + JSON.stringify({ api: api.origin, vehicleId }) + ';\n');
console.log('Frontend construido en ' + fileURLToPath(dist));
