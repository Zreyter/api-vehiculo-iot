import config from '../config.js';

export const vehicleId = config.vehicleId;
const tokenKey = 'excavadora.access:' + new URL(config.api).origin;

function readCode(storage) {
  try { return window[storage].getItem(tokenKey) || ''; }
  catch { return ''; }
}

function saveCode(storage, code) {
  try {
    if (code) window[storage].setItem(tokenKey, code);
    else window[storage].removeItem(tokenKey);
    return true;
  } catch { return false; }
}

/** Envía catálogo por HTTPS y control, observación y confirmaciones por WSS. */
export class VehicleApi extends EventTarget {
  constructor() {
    super();
    this.pending = new Map();
    this.requestId = 0;
  }

  async get(path, signal) {
    return this.request(path, { signal });
  }

  async post(path, body, signal) {
    return this.request(path, { method: 'POST', body: JSON.stringify(body), signal });
  }

  async request(path, options) {
    const url = new URL(path, config.api);
    const headers = { Authorization: 'Bearer ' + this.token };
    if (options.body) headers['Content-Type'] = 'application/json';
    if (url.hostname.endsWith('.ngrok-free.dev') || url.hostname.endsWith('.ngrok-free.app')) {
      headers['ngrok-skip-browser-warning'] = '1';
    }
    const response = await fetch(url, { ...options, headers, cache: 'no-store' });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === 'string' ? body.detail : 'Error HTTP ' + response.status);
    }
    return response.json();
  }

  open(token, role) {
    this.token = token;
    const url = new URL('/ws/vehiculos/' + vehicleId, config.api);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    const protocolToken = btoa(token).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const socket = new WebSocket(url, [role, 'token.' + protocolToken]);
    this.socket = socket;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error('La API no respondió a tiempo.'));
        socket.close();
      }, 6000);
      socket.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
      socket.addEventListener('close', () => {
        clearTimeout(timer);
        reject(new Error('Revisa el código de acceso y la conexión con la API.'));
        if (this.socket !== socket) return;
        this.socket = null;
        for (const pending of this.pending.values()) pending.reject(new Error('Conexión interrumpida.'));
        this.dispatchEvent(new Event('disconnect'));
      }, { once: true });
      socket.addEventListener('message', event => {
        if (this.socket !== socket) return;
        const data = JSON.parse(event.data);
        if (data.tipo === 'respuesta') {
          const pending = this.pending.get(data.id);
          if (data.ok) pending?.resolve(data.datos);
          else pending?.reject(Object.assign(new Error(data.error), { status: data.estado_http }));
        } else {
          this.dispatchEvent(new CustomEvent('vehicle', { detail: data }));
        }
      });
    });
  }

  call(accion, datos = {}, timeout = 4000) {
    return new Promise((resolve, reject) => {
      if (this.socket?.readyState !== WebSocket.OPEN) {
        reject(new Error('Conecta la página a la excavadora.'));
        return;
      }
      const id = ++this.requestId;
      const settle = callback => result => {
        clearTimeout(timer);
        this.pending.delete(id);
        callback(result);
      };
      const timer = setTimeout(() => {
        this.pending.get(id)?.reject(new Error('La API no confirmó la solicitud.'));
      }, timeout);
      const pending = { resolve: settle(resolve), reject: settle(reject) };
      this.pending.set(id, pending);
      try { this.socket.send(JSON.stringify({ id, accion, datos })); }
      catch (error) { pending.reject(error); }
    });
  }

  close() { this.socket?.close(); }
}

/** Comparte la sesión entre páginas y solo recuerda el código con permiso explícito. */
export class AccessForm {
  constructor(api, role, content, onConnect = async () => {}) {
    const form = document.querySelector('#login');
    const input = document.querySelector('#token');
    const remember = document.querySelector('#remember-code');
    const submit = form.querySelector('button');
    const status = document.querySelector('#status');
    const notice = document.querySelector('#notice');
    const swagger = document.querySelector('[data-swagger]');
    if (swagger) swagger.href = new URL('/docs', config.api);
    const connect = async () => {
      if (submit.disabled || !form.checkValidity()) return;
      submit.disabled = true;
      notice.textContent = '';
      status.textContent = 'Conectando…';
      const code = input.value;
      try {
        await api.open(code, role);
        await onConnect();
        if (!api.socket) throw new Error('Se cerró la conexión con la API.');
        saveCode('sessionStorage', code);
        if (!saveCode('localStorage', remember.checked ? code : '') && remember.checked) {
          remember.checked = false;
          notice.textContent = 'El navegador no pudo recordar el código.';
        }
        form.hidden = true;
        content.hidden = false;
        status.textContent = 'Conectado';
      } catch (error) {
        api.close();
        notice.textContent = error.message;
        status.textContent = 'Sin conexión';
      } finally {
        submit.disabled = false;
      }
    };
    api.addEventListener('disconnect', () => {
      status.textContent = 'Sin conexión';
      content.hidden = true;
      form.hidden = false;
    });
    form.addEventListener('submit', event => { event.preventDefault(); connect(); });
    remember.addEventListener('change', () => { if (!remember.checked) saveCode('localStorage', ''); });
    document.querySelector('#logout').addEventListener('click', () => {
      saveCode('sessionStorage', '');
      saveCode('localStorage', '');
      remember.checked = false;
      input.value = '';
      api.close();
    });
    window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
    const saved = readCode('localStorage');
    remember.checked = Boolean(saved);
    input.value = readCode('sessionStorage') || saved;
    if (input.value) connect();
  }
}
