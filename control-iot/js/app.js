import { AccessForm, VehicleApi, vehicleId } from './api.js';
import { Joystick, bucketDirections, vehicleDirections } from './joystick.js';
import { AssistPanel } from './assist-panel.js';

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
    this.assist = new AssistPanel(this);
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
      if (!detail.id_ejecucion || !['demo_finalizada', 'demo_cancelada', 'error'].includes(detail.tipo)) return;
      if (detail.id_ejecucion === this.execution) this.finishDemo(detail);
      else if (this.startingDemo) this.earlyDemo = detail;
    });
    this.api.addEventListener('disconnect', () => {
      this.revision++;
      this.commands = null;
      this.assist.cancel();
      if (this.assist.dialog.open) this.assist.dialog.close();
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

  finishDemo(detail) {
    this.execution = null;
    if (detail.mensaje) this.show(detail.mensaje);
    else if (detail.tipo === 'demo_finalizada') {
      const { pasos_enviados: sent, pasos_sin_envio: skipped } = detail;
      this.show(Number.isInteger(sent) && Number.isInteger(skipped)
        ? `Demo completada. Envíos a la placa: ${sent} de ${sent + skipped}.`
        : 'Demo completada.');
    } else this.show('Demo cancelada.');
    this.render();
  }

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
    $('open-assist').disabled = !this.commands || this.api.socket?.readyState !== WebSocket.OPEN;
    for (const stick of this.sticks || []) stick.element.setAttribute('aria-disabled', String(!armed));
    document.querySelectorAll('[data-code]').forEach(button => {
      button.disabled = !armed || !this.commands?.has(Number(button.dataset.code));
    });
    this.assist?.render();
  }

  activate() {
    if (this.busy || this.stopping || !this.commands || this.execution || this.assist.running || document.hidden) return false;
    const armed = this.controller.arm({ commands: this.commands, transport: 'wifi' });
    if (armed) this.show('');
    return armed;
  }

  canUseAssist() {
    return this.assist.dialog.open && this.api.socket?.readyState === WebSocket.OPEN &&
      this.commands && !this.busy && !this.stopping && !this.execution &&
      !this.controller.snapshot().armed && !document.hidden;
  }

  press(code, source) {
    if (code === 0) { void this.stop(); return; }
    if (this.assist.dialog.open !== (source === 'camera')) return;
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
    if (!this.api.socket || (code !== 0 && options.stillWanted?.() === false)) return cancelledOrder;
    const revision = this.revision;
    const action = actions.find(item => item.code === code);
    const data = { codigo: action.wireCode ?? code, intencion: ++this.intent };
    if (data.codigo === 9) data.pulso_ms = action.duration;
    if (options.duration !== undefined) data.duracion_ms = options.duration;
    const result = await this.api.call('entrada', data);
    if (revision !== this.revision || data.intencion !== this.intent || result.cancelado) return result;
    this.lease = result.sesion_activa === true;
    if (result.orden_enviada) this.show(code === 0 ? 'Parada enviada por WebSocket' : 'Orden enviada por WebSocket');
    else if (code && result.recibida) this.show('Orden recibida por la API. ' + (result.mensaje || ''));
    return result;
  }

  stop() {
    this.revision++;
    if (this.stopping) return this.stopping;
    this.assist.cancel();
    this.stopping = this.release().finally(() => { this.stopping = null; this.render(); });
    this.render();
    return this.stopping;
  }

  async release() {
    // Se libera la sesión por el mismo canal, aunque una orden siga en vuelo.
    this.lease = false;
    const cancel = this.execution || this.startingDemo;
    this.execution = null;
    const idle = this.controller.halt();
    this.resetSticks();
    try {
      const jobs = [];
      if (this.api.socket) jobs.push(this.api.call('liberar'));
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
      else if (this.earlyDemo?.id_ejecucion === result.id_ejecucion) this.finishDemo(this.earlyDemo);
      else this.execution = result.id_ejecucion;
    } catch (error) {
      this.show(error.message);
      await this.stop();
    } finally {
      this.earlyDemo = null;
      this.startingDemo = this.busy = false;
      this.render();
    }
  }

  async heartbeat() {
    const revision = this.revision;
    if (this.renewing === revision || (!this.execution && !this.lease)) return;
    this.renewing = revision;
    const execution = this.execution;
    const intent = this.intent;
    try {
      const result = await this.api.call(execution ? 'demo_latido' : 'latido', {}, heartbeatTimeout);
      if (!execution && result.sesion_activa === false && revision === this.revision && intent === this.intent) {
        this.lease = false;
      }
    }
    catch (error) {
      if (revision === this.revision && execution && this.execution === execution) {
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
    const action = $('binding-action');
    const key = $('binding-key');
    const notice = $('binding-notice');
    action.replaceChildren(...actions.map(item => new Option(item.name, item.code)));
    const refresh = () => {
      key.value = this.keys[action.value];
      notice.textContent = '';
    };
    action.onchange = refresh;
    key.addEventListener('keydown', event => {
      if (event.code === 'Tab' || event.code === 'Escape') return;
      event.preventDefault();
      if (Object.entries(this.keys).some(([code, value]) => code !== action.value && value === event.code)) {
        notice.textContent = 'Esa tecla ya está asignada.';
        return;
      }
      this.keys[action.value] = key.value = event.code;
      localStorage.setItem(keysStorage, JSON.stringify(this.keys));
      notice.textContent = '';
    });
    $('reset-keys').onclick = () => {
      localStorage.removeItem(keysStorage);
      this.keys = { ...defaults };
      refresh();
    };
    refresh();
    $('open-bindings').onclick = () => this.openDialog('key-settings');
    $('open-assist').onclick = () => {
      this.assist.select();
      this.openDialog('assist-settings');
    };
  }

  openDialog(id) {
    if (this.controller.snapshot().armed || this.execution || this.startingDemo) void this.stop();
    $(id).showModal();
    this.render();
  }

  bindInputs() {
    window.addEventListener('keydown', event => {
      if (event.repeat || event.altKey || event.ctrlKey || event.metaKey || !this.api.socket ||
          event.target.closest?.('input,select,[contenteditable]')) return;
      if (this.assist.dialog.open && event.target.closest?.('button')) return;
      const action = actions.find(item => this.keys[item.code] === event.code);
      if (!action) return;
      event.preventDefault();
      this.press(action.code, 'key:' + event.code);
    });
    window.addEventListener('keyup', event => this.releaseInput('key:' + event.code));
    document.addEventListener('visibilitychange', () => { if (document.hidden) void this.stop(); });
    window.addEventListener('blur', () => {
      if (this.controller.snapshot().armed || this.execution || this.startingDemo || this.assist.running || this.assist.listener) void this.stop();
    });
    window.addEventListener('pagehide', () => { this.assist.cancel(); this.api.close(); });
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
