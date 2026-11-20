import config from '../config.js';
import { VehicleApi } from './api.js';

const api = new VehicleApi();
const $ = id => document.getElementById(id);
const login = $('acceso'), form = $('modelo'), editor = $('editor');
const pageSize = 15;
let start = 0, filter = '', editing = null, reads = 0;
const labels = { total_modelos: 'Modelos', total_unidades: 'Unidades', asignadas: 'Asignadas',
  exhibicion: 'En exhibición', sin_clasificar: 'Sin clasificar', clientes: 'Clientes activos', demos: 'Demos activas' };

function session(active, message = '') {
  ++reads;
  login.hidden = active || !config.comercial;
  $('inventario').hidden = $('salir').hidden = !active;
  $('aviso').textContent = message;
  if (!active) {
    api.token = '';
    $('metricas').replaceChildren();
    $('filas').replaceChildren();
    if (editor.open) editor.close();
  }
}

function node(tag, text) {
  const element = document.createElement(tag);
  element.textContent = text;
  return element;
}

function openEditor(item) {
  const cliente = $('vista').value === 'clientes';
  editing = item?.id_modelo ?? item?.id_usuario ?? null;
  form.reset();
  $('titulo-editor').textContent = (item ? 'Editar ' : 'Nuevo ') + (cliente ? 'cliente' : 'modelo');
  form.elements.nombre.maxLength = cliente ? 120 : 80;
  form.elements.nombre.value = item?.nombre || '';
  form.elements.descripcion.value = item?.descripcion || '';
  form.elements.correo.value = item?.correo || '';
  form.elements.correo.required = cliente;
  form.elements.clave.required = cliente && !item;
  form.elements.activo.checked = item?.activo ?? true;
  form.elements.activo.disabled = cliente && !item;
  $('activo-label').textContent = cliente ? 'Cuenta activa' : 'Modelo activo';
  $('correo-cliente').hidden = !cliente;
  $('clave-cliente').hidden = !form.elements.clave.required;
  $('descripcion-modelo').hidden = cliente;
  $('error-editor').textContent = '';
  editor.showModal();
  form.elements.nombre.focus();
}

const columns = {
  modelos: ['ID','Modelo','Estado','Acción'],
  unidades: ['ID','Unidad','Modelo','Estado'],
  clientes: ['ID','Cliente','Correo','Estado','Acción'],
};

function table(rows, view) {
  const head = document.createElement('tr');
  for (const name of columns[view]) {
    const cell = node('th', name);
    cell.scope = 'col';
    head.append(cell);
  }
  $('cabecera').replaceChildren(head);
  const list = rows.slice(0, pageSize).map(item => {
    const row = document.createElement('tr');
    const status = item.activo ? 'Activo' : 'Inactivo';
    let values;
    if (view === 'unidades') values = [item.id_vehiculo, item.nombre, item.modelo, item.estado.replaceAll('_',' ')];
    if (view === 'clientes') values = [item.id_usuario, item.nombre, item.correo, status];
    if (view === 'modelos') values = [item.id_modelo, item.nombre, status];
    for (const value of values) row.append(node('td',value));
    if (view !== 'unidades') {
      const edit = node('button','Editar');
      edit.type = 'button';
      edit.setAttribute('aria-label','Editar ' + item.nombre);
      edit.onclick = () => openEditor(item);
      row.insertCell().append(edit);
    }
    return row;
  });
  $('filas').replaceChildren(...list);
  $('rango').textContent = list.length ? (start + 1) + '–' + (start + list.length) : 'Sin resultados';
  $('anterior').disabled = start === 0;
  $('siguiente').disabled = rows.length <= pageSize;
}

async function refresh() {
  const version = ++reads;
  const view = $('vista').value;
  $('filas').replaceChildren();
  $('rango').textContent = '';
  $('aviso').textContent = 'Consultando inventario…';
  $('nuevo').hidden = view === 'unidades';
  $('nuevo').textContent = view === 'clientes' ? 'Nuevo cliente' : 'Nuevo modelo';
  $('anterior').disabled = $('siguiente').disabled = true;
  const params = new URLSearchParams({ buscar: filter, inicio: start, limite: pageSize + 1 });
  try {
    const [counts, rows] = await Promise.all([api.get('/comercial/resumen'), api.get('/comercial/' + view + '?' + params)]);
    if (version !== reads) return;
    $('metricas').replaceChildren(...Object.entries(labels).map(([key,label]) => {
      const group = document.createElement('div');
      group.append(node('dt',label),node('dd',counts[key]));
      return group;
    }));
    table(rows,view);
    $('aviso').textContent = '';
  } catch (err) {
    if (version !== reads) return;
    if (err.status === 401 || err.status === 403) session(false,err.message);
    else {
      $('filas').replaceChildren(); $('rango').textContent = '';
      $('aviso').textContent = 'Inventario sin actualizar. ' + err.message;
    }
  }
}

login.onsubmit = async event => {
  event.preventDefault();
  const submit = login.querySelector('button');
  submit.disabled = true;
  try {
    const result = await api.post('/comercial/acceso',{ correo: login.elements.correo.value, clave: login.elements.clave.value });
    api.token = result.token;
    login.elements.clave.value = '';
    if (result.rol !== 'admin') {
      await api.request('/comercial/sesion',{ method: 'DELETE' });
      session(false,'Se requiere una cuenta de administrador.');
      return;
    }
    start = 0; filter = ''; $('filtro').reset();
    session(true);
    await refresh();
  } catch (err) { session(false,err.message); }
  finally { submit.disabled = false; }
};

$('salir').onclick = async () => {
  try { await api.request('/comercial/sesion',{ method: 'DELETE' }); session(false,'Sesión cerrada.'); }
  catch (err) { $('aviso').textContent = 'No se pudo confirmar la salida. ' + err.message; }
};
$('vista').onchange = () => { start = 0; void refresh(); };
$('filtro').onsubmit = event => { event.preventDefault(); filter = $('filtro').elements.buscar.value.trim(); start = 0; void refresh(); };
$('anterior').onclick = () => { start = Math.max(0,start-pageSize); void refresh(); };
$('siguiente').onclick = () => { start += pageSize; void refresh(); };
$('nuevo').onclick = () => openEditor(null);
$('cancelar').onclick = () => editor.close();
form.onsubmit = async event => {
  event.preventDefault();
  const save = form.querySelector('.primary');
  if (save.disabled) return;
  const collection = $('vista').value;
  const data = { nombre: form.elements.nombre.value.trim(), activo: form.elements.activo.checked };
  if (collection === 'clientes') {
    data.correo = form.elements.correo.value.trim();
    if (editing === null) {
      delete data.activo;
      data.clave = form.elements.clave.value;
    }
  } else data.descripcion = form.elements.descripcion.value.trim();
  save.disabled = $('cancelar').disabled = true;
  try {
    if (editing === null) await api.post('/comercial/' + collection,data);
    else await api.request('/comercial/' + collection + '/' + editing,{ method:'PUT', body:JSON.stringify(data) });
    editor.close();
    await refresh();
  } catch (err) {
    if (err.status === 401 || err.status === 403) session(false,err.message);
    else $('error-editor').textContent = err.message;
  } finally { save.disabled = $('cancelar').disabled = false; }
};
editor.addEventListener('close', () => { form.elements.clave.value = ''; });
editor.addEventListener('cancel', event => { if (form.querySelector('.primary').disabled) event.preventDefault(); });
session(false,config.comercial ? '' : 'Administración aún no está habilitada en este entorno.');
