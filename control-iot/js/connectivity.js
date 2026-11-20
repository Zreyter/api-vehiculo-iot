export class Connectivity {
  constructor(api, vehicleId) {
    this.vehicleId = vehicleId;
    this.api = api;
    api.addEventListener('online', () => this.socket('En línea', 'ready'));
    const check = () => { if (!document.hidden) void this.check(); };
    const timer = setInterval(check, 30000);
    document.addEventListener('visibilitychange', check);
    window.addEventListener('pagehide', () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', check);
    }, { once: true });
    check();
  }

  socket(message, state) {
    const element = document.querySelector('#ws-health');
    element.dataset.state = state;
    element.textContent = message === 'Sin conexión' ? 'Desconectado' : message;
  }

  async check() {
    if (this.checking) return;
    this.checking = true;
    const indicator = document.querySelector('#api-health');
    indicator.textContent = 'Comprobando';
    try {
      if (this.api.token) {
        indicator.parentElement.title = 'Disponibilidad HTTPS de la consulta de estado del dispositivo';
        const status = await this.api.get('/vehiculos/' + this.vehicleId + '/dispositivo');
        if (typeof status?.conectado !== 'boolean') throw new Error('Estado desconocido');
      } else {
        indicator.parentElement.title = 'Disponibilidad HTTPS del contrato OpenAPI';
        const contract = await this.api.get('/openapi.json');
        if (!contract?.openapi || !contract.paths?.['/vehiculos/{id_vehiculo}/historial']) {
          throw new Error('Contrato desconocido');
        }
      }
      indicator.textContent = 'Disponible';
      indicator.dataset.state = 'ready';
    } catch {
      indicator.textContent = 'No disponible';
      indicator.dataset.state = 'offline';
    } finally { this.checking = false; }
  }
}
