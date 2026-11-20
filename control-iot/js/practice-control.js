const key = event => JSON.stringify([event.tipo, event.id_vehiculo, event.id_comando,
  event.id_ejecucion, event.marca_temporal]);

export class PracticeControl {
  constructor(api, receipt, vehicleId) {
    this.base = '/vehiculos/' + vehicleId;
    this.api = api;
    this.receipt = receipt;
    this.serial = Promise.resolve();
    this.events = new Set();
    this.ticket = 0;
    this.enabled = false;
    api.addEventListener('vehicle', ({ detail }) => {
      if (!this.enabled || detail.id_vehiculo !== vehicleId ||
          !['movimiento_individual', 'demo_iniciada', 'demo_cancelada'].includes(detail.tipo)) return;
      const id = key(detail);
      this.events.add(id);
      if (this.events.size > 64) this.events.delete(this.events.values().next().value);
      if (this.accepted?.key === id) this.report();
    });
  }

  clear() {
    this.ticket++;
    this.execution = null;
    this.events.clear();
    this.accepted = null;
    this.receipt.hidden = true;
    this.receipt.textContent = '';
  }

  report() {
    const { label, key: id } = this.accepted;
    this.receipt.textContent = label + ' · Aceptado por API (HTTP)' +
      (this.events.has(id) ? ' · Evento WSS recibido' : ' · Esperando evento WSS');
  }

  requested(label) {
    this.accepted = null;
    this.receipt.hidden = false;
    this.receipt.textContent = label + ' · Solicitado';
    return ++this.ticket;
  }

  async request(label, ticket, send) {
    try {
      const event = await send();
      if (ticket === this.ticket) {
        this.accepted = { label, key: key(event) };
        this.report();
      }
      return event;
    } catch (error) {
      if (ticket === this.ticket) this.receipt.textContent = label + ' · ' + error.message;
      throw error;
    }
  }

  move(code, options) {
    const id = this.commands.get(code);
    if (!id) return Promise.reject(new Error('Comando ausente del catálogo activo.'));
    const label = code === 0 ? 'Detener' : globalThis.VehicleDrive.actions.find(action => action.code === code).name;
    const ticket = this.requested(label);
    // Una parada invalida entradas pendientes. Espera la escritura en curso para quedar última en BD.
    const job = this.serial.then(async () => {
      if (ticket !== this.ticket || (code && options.stillWanted?.() === false)) return { cancelado: true };
      await this.request(label, ticket, () => this.api.post(this.base + '/movimientos',
        { id_comando: id, origen: 'Control REST' }));
      return { salidas_confirmadas: false };
    });
    this.serial = job.catch(() => {});
    return job;
  }

  async startDemo(id) {
    const label = 'Inicio de demo';
    const ticket = this.requested(label);
    const event = await this.request(label, ticket, () => this.api.post(this.base + '/demos', { id_demo: id, modo: 'registro' }));
    this.execution = event;
    return event;
  }

  isCurrentDemo(event) {
    return this.execution?.id_demo === event.id_demo &&
      Date.parse(event.marca_temporal) >= Date.parse(this.execution.marca_temporal);
  }

  async cancelDemo() {
    this.execution = null;
    const label = 'Cancelación de demo';
    return this.request(label, this.requested(label), () => this.api.request(this.base + '/demos/activa', { method: 'DELETE' }));
  }
}
