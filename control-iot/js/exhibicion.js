import config from '../config.js';
import { VehicleApi } from './api.js';
import { Joystick, vehicleDirections } from './joystick.js';

const api = new VehicleApi(), $ = id => document.getElementById(id);
let conexion;
let conducir;
const palanca = new Joystick($('exhibicion-stick'), vehicleDirections, {
  enabled: () => Boolean(conducir),
  press: codigo => conducir?.mover(codigo),
  release: () => conducir?.soltar(),
});
const teclas = { ArrowUp: 2, w: 2, ArrowDown: 3, s: 3, ArrowLeft: 10, a: 10, ArrowRight: 13, d: 13 };
let teclaActiva;
$('exhibicion-stick').addEventListener('keydown', e => {
  const codigo = teclas[e.key];
  if (!conducir || !codigo) return;
  e.preventDefault();
  if (e.repeat) return;
  teclaActiva = e.key;
  conducir.mover(codigo);
  palanca.showInput([codigo]);
});
$('exhibicion-stick').addEventListener('keyup', e => {
  if (e.key !== teclaActiva) return;
  e.preventDefault();
  liberar();
});
function liberar() {
  teclaActiva = null;
  palanca.showInput([]);
  palanca.clear();
}
$('exhibicion-stick').addEventListener('blur', liberar);
window.addEventListener('blur', liberar);
document.addEventListener('visibilitychange', () => { if (document.hidden) liberar(); });
function iniciar(unidad) {
  if (conexion) return;
  const url = new URL('/exhibicion/ws/' + unidad.id_vehiculo,config.api);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(url);
  conexion = socket;
  $('aviso').textContent = 'Solicitando prueba.';
  let pulso, cuenta, repeticion;
  let activo = 0;
  let permitidos = new Set();
  const enviar = datos => {
    if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(datos));
  };
  const soltar = () => {
    clearInterval(repeticion);
    repeticion = null;
    if (activo) enviar({codigo: 0});
    activo = 0;
  };
  socket.onmessage = e => {
    const mensaje = JSON.parse(e.data);
    if (mensaje.tipo === 'error') $('aviso').textContent = mensaje.detalle;
    if (mensaje.tipo === 'inicio') {
      permitidos = new Set(Object.keys(mensaje.comandos).map(Number));
      conducir = {
        soltar,
        mover(codigo) {
          soltar();
          if (!permitidos.has(codigo)) return;
          activo = codigo;
          enviar({codigo});
          repeticion = setInterval(() => enviar({codigo: activo}),160);
        },
      };
      $('exhibicion-stick').setAttribute('aria-disabled','false');
      const vence = Date.now() + mensaje.segundos * 1000;
      const actualizar = () => { $('tiempo').textContent = Math.max(0,Math.ceil((vence-Date.now())/1000)) + ' s'; };
      $('acciones').replaceChildren(...Object.entries(mensaje.comandos).filter(([codigo]) => [1,4].includes(Number(codigo))).map(([codigo,nombre]) => {
        const boton = document.createElement('button');
        boton.type = 'button';
        boton.textContent = nombre;
        boton.onclick = () => { liberar(); enviar({codigo:Number(codigo)}); };
        return boton;
      }));
      $('prueba').hidden = false;
      $('aviso').textContent = '';
      $('detener').onclick = () => {
        liberar();
        conducir = null;
        enviar({accion:'detener'});
        $('prueba').hidden = true;
      };
      actualizar();
      cuenta = setInterval(actualizar,250);
      pulso = setInterval(() => enviar({accion:'latido'}),240);
    }
  };
  socket.onclose = () => {
    soltar();
    conducir = null;
    liberar();
    $('exhibicion-stick').setAttribute('aria-disabled','true');
    clearInterval(cuenta);
    clearInterval(pulso);
    conexion = null;
    $('prueba').hidden = true;
    if (!$('aviso').textContent || $('aviso').textContent === 'Solicitando prueba.') {
      $('aviso').textContent = 'La prueba terminó o no hay una unidad disponible.';
    }
    void cargar(false);
  };
}
window.addEventListener('pagehide', () => { liberar(); conexion?.close(); });

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
