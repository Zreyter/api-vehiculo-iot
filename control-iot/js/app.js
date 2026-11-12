import { AccessForm, VehicleApi, vehicleId } from './api.js';
import { Joystick, bucketDirections, vehicleDirections } from './joystick.js';

const $ = id => document.getElementById(id);
const { actions, resolveCommands, createController, gamepadInputs } = globalThis.VehicleDrive;
const keysStorage = 'excavadora.keys';
const heartbeatTimeout = 650;
const cancelledOrder = { cancelado: true };

/** Coordina las entradas manuales, la sesión de control y las demos de esta pestaña. */
class DrivePage {
  constructor() {
    this.api = new VehicleApi();
    this.intent = 0;
    this.revision = 0;
    this.padInputs = new Set();
    this.stickInputs = new Map();
    this.controller = createController({
      pulseCodes: [4],
      send: (code, _target, options) => this.send(code, options),
      changed: () => this.render(),
      fault: error => { this.show(error.message); void this.stop(); },
      notice: message => this.show(message),
    });
    const inputs = { enabled: () => this.controller.snapshot().armed,
      press: (code, source) => this.press(code, source),
      release: source => this.controller.release(source) };
    this.sticks = [
      new Joystick($('vehicle-stick'), vehicleDirections, inputs),
      new Joystick($('bucket-stick'), bucketDirections, inputs),
    ];
    $('arm').onclick = () => this.activate();
    $('stop').onclick = () => this.stop();
    $('run-demo').onclick = () => this.execution ? this.stop() : this.runDemo();
    $('demo').onchange = () => this.render();
    document.querySelectorAll('[data-code]').forEach(button => {
      button.onclick = () => {
        const code = Number(button.dataset.code);
        this.press(code, 'button:' + code);
        this.controller.release('button:' + code);
      };
    });
    this.api.addEventListener('vehicle', ({ detail }) => {
      if (this.execution && detail.id_ejecucion === this.execution &&
          ['demo_finalizada', 'demo_cancelada', 'error'].includes(detail.tipo)) {
        this.execution = null;
        if (detail.mensaje) this.show(detail.mensaje);
        else if (detail.orden_enviada && detail.tipo === 'demo_finalizada') this.show('Demo enviada por WebSocket');
        this.render();
      }
    });
    this.api.addEventListener('disconnect', () => {
      this.revision++;
      this.execution = null;
      this.lease = false;
      this.showDevice('Consultando la placa');
      this.resetSticks();
      void this.controller.halt();
      this.render();
    });
    new AccessForm(this.api, 'iot-control', $('controls'), () => this.load());
    this.configureKeys();
    this.bindInputs();
    setInterval(() => void this.heartbeat(), 150);
    setInterval(() => void this.refreshDevice(), 1500);
    this.render();
  }

  async load() {
    const base = '/admin/vehiculos/' + vehicleId;
    const [commands, demos] = await Promise.all([this.api.get(base + '/comandos'), this.api.get(base + '/demos')]);
    this.commands = resolveCommands(commands).map;
    this.commands.set(0, 0);
    $('demo').replaceChildren(new Option('Selecciona una demo', ''));
    for (const demo of demos.filter(d => d.activo === 1)) {
      $('demo').add(new Option(demo.nombre, demo.id_demo));
    }
    this.render();
    void this.refreshDevice();
  }

  show(message) { $('notice').textContent = message || ''; }

  showDevice(message) {
    const status = $('device-status');
    if (status.textContent !== message) status.textContent = message;
  }

  async refreshDevice() {
    const socket = this.api.socket;
    if (socket?.readyState !== WebSocket.OPEN || this.checkingDevice === socket || document.hidden) return;
    this.checkingDevice = socket;
    try {
      const device = await this.api.call('estado', {}, 1000);
      if (this.api.socket !== socket) return;
      const label = device.listo ? 'Placa lista por WebSocket' : device.conectado
        ? 'Placa conectada · control WiFi pendiente' : 'Placa sin conexión';
      this.showDevice(label);
    } catch {
      if (this.api.socket === socket) this.showDevice('Estado de la placa no disponible');
    } finally {
      if (this.checkingDevice === socket) this.checkingDevice = null;
    }
  }

  render() {
    const armed = this.controller.snapshot().armed;
    $('arm').disabled = this.busy || !!this.stopping || armed || !!this.execution;
    $('arm').textContent = armed ? 'Control activo' : 'Activar control';
    $('run-demo').disabled = this.busy || (!this.execution && !$('demo').value);
    $('run-demo').textContent = this.execution ? 'Cancelar demo' : 'Ejecutar demo';
    $('demo').disabled = this.busy || !!this.execution;
    for (const stick of this.sticks || []) stick.element.setAttribute('aria-disabled', String(!armed));
    document.querySelectorAll('[data-code]').forEach(button => {
      button.disabled = !armed || !this.commands?.has(Number(button.dataset.code));
    });
  }

  activate() {
    if (this.busy || this.stopping || !this.commands || this.execution || document.hidden) return;
    if (this.controller.arm({ commands: this.commands, transport: 'wifi' })) this.show('');
  }

  async acquireForOrder() {
    const revision = this.revision;
    const socket = this.api.socket;
    this.acquiring = socket;
    try {
      await this.api.call('activar');
      if (revision !== this.revision || this.api.socket !== socket) return cancelledOrder;
      if (document.hidden) { void this.stop(); return cancelledOrder; }
      this.lease = true;
      this.intent = 0;
    } catch (error) {
      if (revision !== this.revision || this.api.socket !== socket) return cancelledOrder;
      if (error.status === 409) {
        void this.refreshDevice();
        return { cancelado: true, requiere_nueva_entrada: true, mensaje: error.message };
      }
      // Una adquisición que excedió el plazo podría completarse en el servidor.
      await this.api.call('liberar').catch(() => {});
      throw error;
    } finally {
      this.acquiring = null;
    }
  }

  press(code, source) {
    if (code === 0) { void this.stop(); return; }
    if (code === 8) { if (!document.hidden) void this.runDemo(); return; }
    if (document.hidden || !this.controller.press(code, source)) return;
    if (source.startsWith('key:') || source.startsWith('pad:')) {
      this.stickInputs.set(source, code);
      this.showStickInputs();
    }
  }

  showStickInputs() {
    const commands = Array.from(this.stickInputs.values()).reverse();
    for (const stick of this.sticks) stick.showInput(commands);
  }

  releaseInput(source) {
    this.controller.release(source);
    if (this.stickInputs.delete(source)) this.showStickInputs();
  }

  resetSticks() {
    this.stickInputs.clear();
    this.showStickInputs();
    for (const stick of this.sticks) stick.clear();
  }

  async send(code, options) {
    if (code !== 0) {
      if (options.stillWanted?.() === false) return cancelledOrder;
      if (!this.lease) {
        const result = await this.acquireForOrder();
        if (result) return result;
      }
      if (options.stillWanted?.() === false) return cancelledOrder;
    }
    if (!this.lease) return cancelledOrder;
    const action = actions.find(item => item.code === code);
    const data = { codigo: action.wireCode ?? code, intencion: ++this.intent };
    if (data.codigo === 9) data.pulso_ms = action.duration;
    const result = await this.api.call('orden', data);
    if (result.sesion_finalizada) this.lease = false;
    if (result.orden_enviada && !result.cancelado && (code === 0 || options.stillWanted?.() !== false)) {
      this.show(code === 0 ? 'Parada enviada por WebSocket' : 'Orden enviada por WebSocket');
    }
    return result;
  }

  stop() {
    this.revision++;
    if (this.stopping) return this.stopping;
    this.stopping = this.release().finally(() => { this.stopping = null; this.render(); });
    return this.stopping;
  }

  async release() {
    // Se libera la sesión por el mismo canal, aunque una orden siga en vuelo.
    const hadControl = this.lease || this.acquiring;
    this.lease = false;
    const cancel = this.execution || this.startingDemo;
    this.execution = null;
    const idle = this.controller.halt();
    this.resetSticks();
    try {
      const jobs = [];
      if (hadControl) jobs.push(this.api.call('liberar'));
      if (cancel) jobs.push(this.api.call('demo_cancelar'));
      for (const result of await Promise.all(jobs)) {
        if (result.orden_enviada) this.show('Parada enviada por WebSocket');
        else if (result.salidas_confirmadas === false) this.show(result.mensaje);
      }
    } catch (error) { if (this.api.socket) this.show(error.message); }
    await idle;
  }

  async runDemo() {
    const id = Number($('demo').value);
    if (this.busy || this.stopping || this.execution || !id || document.hidden) return;
    this.busy = true;
    this.show('');
    this.render();
    try {
      const release = this.stop();
      const revision = this.revision;
      await release;
      if (revision !== this.revision || document.hidden) return;
      this.startingDemo = true;
      const result = await this.api.call('demo_iniciar', { id_demo: id });
      if (revision !== this.revision || document.hidden) await this.stop();
      else this.execution = result.id_ejecucion;
    } catch (error) {
      this.show(error.message);
      await this.stop();
    } finally {
      this.startingDemo = this.busy = false;
      this.render();
    }
  }

  async heartbeat() {
    const revision = this.revision;
    if (this.renewing === revision || (!this.execution && !this.lease)) return;
    this.renewing = revision;
    const execution = this.execution;
    try { await this.api.call(execution ? 'demo_latido' : 'latido', {}, heartbeatTimeout); }
    catch (error) {
      if (revision === this.revision && (execution ? this.execution === execution : this.lease)) {
        this.show(error.message);
        await this.stop();
      }
    } finally { if (this.renewing === revision) this.renewing = null; }
  }

  configureKeys() {
    const defaults = Object.fromEntries(actions.map(action => [action.code, action.key]));
    const read = () => {
      try { return JSON.parse(localStorage.getItem(keysStorage)) || {}; } catch { return {}; }
    };
    this.keys = { ...defaults, ...read() };
    const bindings = $('bindings');
    const refresh = () => {
      bindings.replaceChildren();
      for (const action of actions) {
        const label = document.createElement('label');
        label.textContent = action.code === 8 ? 'Ejecutar demo seleccionada' : action.name;
        const input = document.createElement('input');
        input.value = this.keys[action.code];
        input.readOnly = true;
        input.addEventListener('keydown', event => {
          if (event.code === 'Tab' || event.code === 'Escape') return;
          event.preventDefault();
          if (Object.entries(this.keys).some(([code, key]) => Number(code) !== action.code && key === event.code)) {
            this.show('Esa tecla ya está asignada.'); return;
          }
          this.keys[action.code] = input.value = event.code;
          localStorage.setItem(keysStorage, JSON.stringify(this.keys));
          this.show('');
        });
        label.append(input);
        bindings.append(label);
      }
    };
    $('reset-keys').onclick = () => {
      localStorage.removeItem(keysStorage);
      this.keys = { ...defaults };
      refresh();
    };
    refresh();
  }

  bindInputs() {
    window.addEventListener('keydown', event => {
      if (event.repeat || event.altKey || event.ctrlKey || event.metaKey || !this.api.socket ||
          event.target.closest?.('input,select,[contenteditable]')) return;
      const action = actions.find(item => this.keys[item.code] === event.code);
      if (!action) return;
      event.preventDefault();
      this.press(action.code, 'key:' + event.code);
    });
    window.addEventListener('keyup', event => this.releaseInput('key:' + event.code));
    document.addEventListener('visibilitychange', () => { if (document.hidden) void this.stop(); });
    window.addEventListener('blur', () => {
      if (this.controller.snapshot().armed || this.execution || this.startingDemo) void this.stop();
    });
    window.addEventListener('pagehide', () => this.api.close());
    const poll = () => {
      const pad = Array.from(navigator.getGamepads?.() || []).find(p => p?.mapping === 'standard');
      const next = pad ? gamepadInputs(pad, .25, this.padInputs) : new Set();
      const gamepad = pad ? pad.id : 'Pulsa un botón del mando para detectarlo.';
      if ($('gamepad').textContent !== gamepad) $('gamepad').textContent = gamepad;
      for (const action of actions) {
        const binding = action.code === 14 ? 'b6' : action.pad;
        const source = 'pad:' + binding;
        if (this.padInputs.has(binding) && !next.has(binding)) this.releaseInput(source);
        if (this.api.socket && next.has(binding) && !this.padInputs.has(binding)) this.press(action.code, source);
      }
      this.padInputs = next;
      requestAnimationFrame(poll);
    };
    requestAnimationFrame(poll);
  }
}

new DrivePage();

if ('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js').catch(() => {});
window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault();
  $('install').hidden = false;
  $('install').onclick = async () => {
    await event.prompt();
    $('install').hidden = true;
  };
});
