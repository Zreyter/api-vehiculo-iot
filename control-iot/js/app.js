import { AccessForm, VehicleApi, vehicleId } from './api.js';
import { Joystick, bucketDirections, vehicleDirections } from './joystick.js';

const $ = id => document.getElementById(id);
const { actions, resolveCommands, createController, gamepadInputs } = globalThis.VehicleDrive;
const keysStorage = 'excavadora.keys';
const heartbeatTimeout = 650;

/** Coordina las entradas manuales, la sesión de control y las demos de esta pestaña. */
class DrivePage {
  constructor() {
    this.api = new VehicleApi();
    this.intent = 0;
    this.revision = 0;
    this.padInputs = new Set();
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
        this.render();
      }
    });
    this.api.addEventListener('disconnect', () => {
      this.revision++;
      this.execution = null;
      this.lease = false;
      void this.controller.halt();
      this.render();
    });
    new AccessForm(this.api, 'iot-control', $('controls'), () => this.load());
    this.configureKeys();
    this.bindInputs();
    setInterval(() => void this.heartbeat(), 150);
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
  }

  show(message) { $('notice').textContent = message || ''; }

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

  async activate() {
    if (this.busy || !this.commands || this.controller.snapshot().armed || this.execution) return;
    this.busy = true;
    const revision = this.revision;
    this.show('');
    this.render();
    try {
      await this.api.call('activar');
      if (revision !== this.revision || document.hidden) {
        await this.api.call('liberar');
        return;
      }
      this.lease = true;
      this.intent = 0;
      if (!this.controller.arm({ commands: this.commands, transport: 'wifi' })) await this.stop();
    } catch (error) {
      this.show(error.message);
      if (!this.lease) this.api.call('liberar').catch(() => {});
    } finally {
      this.busy = false;
      this.render();
    }
  }

  press(code, source) {
    if (code === 0) { void this.stop(); return; }
    if (code === 8) { if (!document.hidden) void this.runDemo(); return; }
    if (!document.hidden) this.controller.press(code, source);
  }

  async send(code, options) {
    if (!this.lease || (code !== 0 && options.stillWanted?.() === false)) return { cancelado: true };
    const action = actions.find(item => item.code === code);
    const data = { codigo: action.wireCode ?? code, intencion: ++this.intent };
    if (data.codigo === 9) data.pulso_ms = action.duration;
    const result = await this.api.call('orden', data);
    if (result.sesion_finalizada) this.lease = false;
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
    const hadLease = this.lease;
    this.lease = false;
    const cancel = this.execution || this.startingDemo;
    this.execution = null;
    const idle = this.controller.halt();
    for (const stick of this.sticks) stick.clear();
    try {
      const jobs = [];
      if (hadLease || this.busy && !cancel) jobs.push(this.api.call('liberar'));
      if (cancel) jobs.push(this.api.call('demo_cancelar'));
      for (const result of await Promise.all(jobs)) {
        if (result.salidas_confirmadas === false) this.show(result.mensaje);
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
    window.addEventListener('keyup', event => this.controller.release('key:' + event.code));
    document.addEventListener('visibilitychange', () => { if (document.hidden) void this.stop(); });
    window.addEventListener('blur', () => { if (this.lease || this.execution || this.startingDemo) void this.stop(); });
    window.addEventListener('pagehide', () => this.api.close());
    const poll = () => {
      const pad = Array.from(navigator.getGamepads?.() || []).find(p => p?.mapping === 'standard');
      const next = pad ? gamepadInputs(pad, .25, this.padInputs) : new Set();
      const gamepad = pad ? pad.id : 'Pulsa un botón del mando para detectarlo.';
      if ($('gamepad').textContent !== gamepad) $('gamepad').textContent = gamepad;
      for (const action of actions) {
        const binding = action.code === 14 ? 'b6' : action.pad;
        const source = 'pad:' + binding;
        if (this.padInputs.has(binding) && !next.has(binding)) this.controller.release(source);
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
