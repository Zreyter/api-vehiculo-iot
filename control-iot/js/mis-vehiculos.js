import config from '../config.js';
import { buyerKey, VehicleApi } from './api.js';

const api = new VehicleApi();
const $ = id => document.getElementById(id);
const login = $('acceso');
let version = 0;

function mostrarSesion(token) {
  version++;
  api.token = token;
  login.hidden = !!token || !config.comercial;
  $('salir').hidden = $('actualizar').hidden = !token;
  $('unidades').replaceChildren();
}

function tarjeta(unidad) {
  const card = document.createElement('article');
  card.className = 'card';
  const title = document.createElement('h2'), model = document.createElement('p');
  title.textContent = unidad.nombre;
  model.textContent = unidad.modelo + ' · Unidad ' + unidad.id_vehiculo;
  card.append(title, model);
  for (const [nombre, ruta] of [['Controlar', './'], ['Monitorear', './monitor.html']]) {
    const link = document.createElement('a');
    link.href = ruta + '?unidad=' + encodeURIComponent(unidad.id_vehiculo);
    link.textContent = nombre;
    link.setAttribute('aria-label', nombre + ' ' + unidad.nombre);
    card.append(link);
  }
  return card;
}

async function actualizar() {
  const actual = ++version;
  $('aviso').textContent = 'Consultando tus vehículos…';
  $('unidades').replaceChildren();
  try {
    const unidades = await api.get('/comercial/mis-vehiculos');
    if (actual !== version) return;
    $('unidades').replaceChildren(...unidades.map(tarjeta));
    $('aviso').textContent = unidades.length ? '' : 'Todavía no tienes vehículos asignados.';
  } catch (err) {
    if (actual !== version) return;
    if (err.status === 401 || err.status === 403) {
      sessionStorage.removeItem(buyerKey);
      mostrarSesion('');
    }
    $('aviso').textContent = err.message;
  }
}

login.onsubmit = async event => {
  event.preventDefault();
  const submit = login.querySelector('button');
  submit.disabled = true;
  try {
    const data = await api.post('/comercial/acceso', {correo: login.elements.correo.value, clave: login.elements.clave.value});
    login.elements.clave.value = '';
    if (data.rol !== 'usuario') {
      api.token = data.token;
      await api.request('/comercial/sesion', { method: 'DELETE' });
      api.token = '';
      $('aviso').textContent = 'Entra en Administración con tu cuenta de administrador.';
      return;
    }
    sessionStorage.setItem(buyerKey, data.token);
    mostrarSesion(data.token);
    await actualizar();
  } catch (err) { $('aviso').textContent = err.message; }
  finally { submit.disabled = false; }
};

$('salir').onclick = async () => {
  try {
    await api.request('/comercial/sesion', { method: 'DELETE' });
    sessionStorage.removeItem(buyerKey);
    mostrarSesion('');
    $('aviso').textContent = 'Sesión cerrada.';
  } catch (err) { $('aviso').textContent = err.message; }
};
$('actualizar').onclick = actualizar;
window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
mostrarSesion(config.comercial ? sessionStorage.getItem(buyerKey) : '');
if (api.token) void actualizar();
if (!config.comercial) $('aviso').textContent = 'El acceso de compradores aún no está habilitado en este entorno.';
