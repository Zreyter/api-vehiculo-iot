import config from '../config.js';
import { VehicleApi } from './api.js';

const api = new VehicleApi(), $ = id => document.getElementById(id);
let conexion;
function iniciar(unidad) {
  if (conexion) return;
  const url = new URL('/exhibicion/ws/' + unidad.id_vehiculo,config.api);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(url);
  conexion = socket;
  $('aviso').textContent = 'Solicitando prueba…';
  let pulso, cuenta;
  const enviar = datos => {
    if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(datos));
  };
  socket.onmessage = e => {
    const mensaje = JSON.parse(e.data);
    if (mensaje.tipo === 'error') $('aviso').textContent = mensaje.detalle;
    if (mensaje.tipo === 'inicio') {
      const vence = Date.now() + mensaje.segundos * 1000;
      const actualizar = () => { $('tiempo').textContent = Math.max(0,Math.ceil((vence-Date.now())/1000)) + ' s'; };
      $('acciones').replaceChildren(...Object.entries(mensaje.comandos).map(([codigo,nombre]) => {
        const boton = document.createElement('button');
        boton.type = 'button';
        boton.textContent = nombre;
        boton.onclick = () => enviar({codigo:Number(codigo)});
        return boton;
      }));
      $('prueba').hidden = false;
      $('aviso').textContent = '';
      $('detener').onclick = () => {
        enviar({accion:'detener'});
        $('prueba').hidden = true;
      };
      actualizar();
      cuenta = setInterval(actualizar,250);
      pulso = setInterval(() => enviar({accion:'latido'}),240);
    }
  };
  socket.onclose = () => {
    clearInterval(cuenta);
    clearInterval(pulso);
    conexion = null;
    $('prueba').hidden = true;
    if (!$('aviso').textContent || $('aviso').textContent === 'Solicitando prueba…') {
      $('aviso').textContent = 'La prueba terminó o no hay una unidad disponible.';
    }
    void cargar(false);
  };
}
window.addEventListener('pagehide', () => conexion?.close());

async function cargar(anunciar = true) {
  try {
    const { modelos, habilitada } = await api.get('/exhibicion/catalogo');
    let libre = false;
    $('catalogo').replaceChildren(...modelos.map(modelo => {
      const card = document.createElement('article');
      card.className = 'card';
      const titulo = document.createElement('h2'), descripcion = document.createElement('p');
      titulo.textContent = modelo.nombre;
      descripcion.textContent = modelo.descripcion;
      card.append(titulo,descripcion);
      for (const unidad of modelo.unidades) {
        const boton = document.createElement('button');
        boton.type = 'button';
        boton.textContent = unidad.disponible ? 'Probar ' + unidad.nombre : unidad.nombre + ' · No disponible';
        boton.disabled = !unidad.disponible;
        boton.onclick = () => iniciar(unidad);
        card.append(boton);
        libre ||= unidad.disponible;
      }
      return card;
    }));
    if (anunciar) $('aviso').textContent = habilitada && libre ? '' : 'Por ahora no hay pruebas públicas disponibles.';
  } catch (error) { $('aviso').textContent = error.message; }
}
if (config.comercial) void cargar();
else $('aviso').textContent = 'Por ahora no hay pruebas públicas disponibles.';
