import { AccessForm, VehicleApi, vehicleId } from './api.js';

// MySQL puede entregar DATETIME sin zona. En ese caso se conserva su hora literal.
function parts(value) {
  if (typeof value !== 'string') return ['—', '—'];
  const local = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.\d+)?$/.exec(value);
  if (local) return [local[3] + '/' + local[2] + '/' + local[1], local[4] + ' (BD)'];
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return ['—', '—'];
  return [date.toLocaleDateString('es-MX', { timeZone: 'UTC' }),
    date.toISOString().slice(11, 19) + ' UTC'];
}

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
    this.sequence = 0;
    this.seenEvents = new Set();
    this.api.addEventListener('disconnect', () => {
      clearTimeout(this.timer);
      this.timer = null;
      this.session?.abort();
      this.session = null;
      this.status('Sin datos actualizados · conexión interrumpida');
      document.querySelector('#last-detail').textContent = 'Último valor conocido · WebSocket desconectado';
    });
    new AccessForm(this.api, 'iot-monitor', document.querySelector('#monitor'), () => this.start());
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && this.session) this.reconcile(true);
    });
    window.addEventListener('pagehide', () => this.api.close());
  }

  status(message) { document.querySelector('#history-status').textContent = message; }

  start() {
    this.session?.abort();
    clearTimeout(this.timer);
    this.timer = null;
    this.session = new AbortController();
    this.inflight = null;
    this.needsHistory = this.needsState = false;
    this.latestEvent = null;
    this.seenEvents.clear();
    this.activity = [];
    this.traffic = [];
    this.renderFrames();
    this.status('Cargando historial…');
    this.reconcile(true);
  }

  last(command, stamp, vehicle) {
    const [date, hour] = parts(stamp);
    document.querySelector('#last-command').textContent = command || 'Sin movimientos';
    document.querySelector('#last-detail').textContent = [vehicle || 'Vehículo ' + vehicleId,
      command && date, command && hour].filter(Boolean).join(' · ');
  }

  // Agrupa ráfagas. Un aviso recibido durante GET exige una nueva lectura al terminar.
  reconcile(state = false) {
    if (!this.session) return;
    this.needsHistory = true;
    this.needsState ||= state;
    if (this.inflight || this.timer) return;
    this.timer = setTimeout(() => { this.timer = null; void this.sync(); }, state ? 0 : 120);
  }

  async sync() {
    const session = this.session;
    if (!session) return;
    this.inflight = session;
    const version = this.sequence;
    const getState = this.needsState;
    this.needsState = this.needsHistory = false;
    const id = vehicleId;
    const readState = async () => {
      if (!getState) return;
      try {
        const state = await this.api.get('/admin/vehiculos/' + id + '/estado', session.signal);
        if (this.session !== session || this.sequence !== version) return;
        if (state && state.id_vehiculo !== id) throw new Error();
        this.last(state?.comando, state?.fecha_actualizacion, state?.vehiculo);
      } catch {
        if (this.session === session && this.sequence === version) {
          document.querySelector('#last-detail').textContent = 'Último estado sin actualizar';
        }
      }
    };
    const readHistory = async () => {
      try {
        const rows = await this.api.get('/vehiculos/' + id + '/historial?limite=10', session.signal);
        if (this.session !== session) return;
        if (!Array.isArray(rows)) throw new Error();
        const seen = new Set();
        this.rows = rows.filter(row => {
          if (row?.id_vehiculo !== id || !Number.isSafeInteger(row.id_historial) || seen.has(row.id_historial)) return false;
          seen.add(row.id_historial);
          return true;
        }).slice(0, 10);
        this.render();
        this.status(this.rows.length ? 'Historial confirmado por la API' : 'Sin movimientos guardados');
      } catch {
        if (this.session === session) this.status('Error al consultar el historial · sin datos actualizados');
      }
    };
    await Promise.all([readState(), readHistory()]);
    if (this.session !== session) return;
    this.inflight = null;
    if (this.needsHistory) this.reconcile(this.needsState);
  }

  receive(event) {
    if (event.tipo === 'historial') return;
    if (['movimiento_individual', 'demo_movimiento'].includes(event.tipo)) {
      if (event.id_vehiculo !== vehicleId || typeof event.comando !== 'string') return;
      const stamp = Date.parse(event.marca_temporal);
      if (!Number.isFinite(stamp)) return;
      const key = JSON.stringify([event.tipo, event.marca_temporal, event.id_comando, event.id_demo, event.orden]);
      if (this.seenEvents.has(key)) return;
      this.seenEvents.add(key);
      if (this.seenEvents.size > 64) this.seenEvents.delete(this.seenEvents.values().next().value);
      if (event.tipo === 'movimiento_individual') this.reconcile();
      if (this.latestEvent == null || stamp >= this.latestEvent) {
        this.latestEvent = stamp;
        this.sequence++;
        this.last(event.comando, event.marca_temporal, event.estado?.vehiculo);
      }
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
    for (const [index, row] of this.rows.entries()) {
      const tr = target.insertRow();
      for (const value of [index + 1, row.comando, ...parts(row.fecha_hora)]) {
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
    const description = [parts(event.marca_temporal)[1], event.direccion || 'API',
      frame.tipo, frame.codigo == null ? '' : 'código ' + frame.codigo].filter(Boolean);
    summary.textContent = description.join(' · ');
    payload.textContent = JSON.stringify(event, null, 2);
    details.append(summary, payload);
    item.append(details);
    return item;
  }
}

new Monitor();
