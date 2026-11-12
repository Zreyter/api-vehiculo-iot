import { AccessForm, VehicleApi } from './api.js';

const time = new Intl.DateTimeFormat('es-MX', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const periodic = new Set(['latido', 'ping', 'pong', 'estado']);
const maxFrames = 40;

/** Mantiene 10 movimientos visibles y un búfer independiente de tramas. */
class Monitor {
  constructor() {
    this.api = new VehicleApi();
    this.rows = [];
    this.frames = document.querySelector('#frames');
    this.heartbeat = document.querySelector('#heartbeat');
    this.activity = [];
    this.traffic = [];
    this.heartbeat.addEventListener('change', () => this.renderFrames());
    this.api.addEventListener('vehicle', ({ detail }) => this.receive(detail));
    new AccessForm(this.api, 'iot-monitor', document.querySelector('#monitor'));
    window.addEventListener('pagehide', () => this.api.close());
  }

  receive(event) {
    if (event.tipo === 'historial') {
      this.rows = event.movimientos;
      this.activity = [];
      this.traffic = [];
      this.renderFrames();
      this.render();
      return;
    }
    if (['movimiento_individual', 'demo_movimiento', 'orden_sin_envio'].includes(event.tipo)) {
      this.rows = [{
        fecha_hora: event.marca_temporal,
        codigo: event.codigo,
        comando: event.comando ?? 'Orden recibida',
        origen: event.tipo === 'orden_sin_envio' ? 'Panel WS (sin envío)'
          : event.tipo === 'demo_movimiento' ? 'Demo ' + event.id_demo + (event.orden_enviada ? ' (enviada)' : '')
          : event.orden_enviada ? 'Panel WS (enviada)' : event.estado?.origen || 'API',
      }, ...this.rows].slice(0, 10);
      this.render();
    }
    this.traffic.unshift(event);
    this.traffic.splice(maxFrames);
    const isPeriodic = event.tipo === 'trama_dispositivo' && periodic.has(event.trama?.tipo);
    if (!isPeriodic) {
      this.activity.unshift(event);
      this.activity.splice(maxFrames);
    }
    if (!isPeriodic || this.heartbeat.checked) {
      this.frames.prepend(this.frame(event));
      if (this.frames.children.length > maxFrames) this.frames.lastElementChild.remove();
      document.querySelector('#empty-frames').hidden = true;
    }
  }

  render() {
    const target = document.querySelector('#movements');
    target.replaceChildren();
    for (const row of this.rows) {
      const tr = target.insertRow();
      for (const value of [time.format(new Date(row.fecha_hora)), row.codigo, row.comando, row.origen]) {
        tr.insertCell().textContent = value ?? '—';
      }
    }
    if (!this.rows.length) {
      const cell = target.insertRow().insertCell();
      cell.colSpan = 4;
      cell.textContent = 'Todavía no hay movimientos.';
    }
  }

  renderFrames() {
    const events = this.heartbeat.checked ? this.traffic : this.activity;
    this.frames.replaceChildren(...events.map(event => this.frame(event)));
    document.querySelector('#empty-frames').hidden = events.length > 0;
  }

  frame(event) {
    const item = document.createElement('li');
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    const payload = document.createElement('pre');
    const frame = event.trama || event;
    const description = [time.format(new Date(event.marca_temporal)), event.direccion || 'API',
      frame.tipo, frame.codigo == null ? '' : 'código ' + frame.codigo].filter(Boolean);
    summary.textContent = description.join(' · ');
    payload.textContent = JSON.stringify(event, null, 2);
    details.append(summary, payload);
    item.append(details);
    return item;
  }
}

new Monitor();
