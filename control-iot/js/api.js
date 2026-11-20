import config from '../config.js';
import { Connectivity } from './connectivity.js';

const unidad = new URLSearchParams(location.search).get('unidad');
const personal = config.comercial && unidad !== null;
export const vehicleId = personal ? Number(unidad) : config.vehicleId;
export const buyerKey = 'excavadora.comprador:' + new URL(config.api).origin;
if (personal) {
  for (const link of document.querySelectorAll('.main-nav a[href="./"], .main-nav a[href="./monitor.html"]')) {
    link.search = new URLSearchParams({ unidad });
  }
}
for (const link of document.querySelectorAll('[data-comercial]')) link.hidden = !config.comercial;
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

function offerPasswordSave(username, password) {
  if (!window.PasswordCredential || !navigator.credentials?.store) return;
  try {
    void navigator.credentials.store(new PasswordCredential({ id: username, password })).catch(() => {});
  } catch {}
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

  async request(path, options = {}) {
    const url = new URL(path, config.api);
    const headers = this.token ? { Authorization: 'Bearer ' + this.token } : {};
    if (options.body) headers['Content-Type'] = 'application/json';
    if (url.hostname.endsWith('.ngrok-free.dev') || url.hostname.endsWith('.ngrok-free.app')) {
      headers['ngrok-skip-browser-warning'] = '1';
    }
    const deadline = new AbortController();
    const abort = () => deadline.abort();
    const timer = setTimeout(abort, 6000);
    if (options.signal?.aborted) abort();
    options.signal?.addEventListener('abort', abort, { once: true });
    try {
      const response = await fetch(url, { ...options, signal: deadline.signal, headers, cache: 'no-store' });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw Object.assign(new Error(typeof body.detail === 'string' ? body.detail : 'Error HTTP ' + response.status), { status: response.status });
      }
      if (response.status === 204) return null;
      return await response.json();
    } catch (error) {
      if (deadline.signal.aborted) throw new Error('La solicitud fue interrumpida o venció su plazo.');
      if (error instanceof SyntaxError) throw new Error('La API devolvió una respuesta no válida.');
      throw error;
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener('abort', abort);
    }
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
      socket.addEventListener('open', () => { clearTimeout(timer); this.dispatchEvent(new Event('online')); resolve(); }, { once: true });
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
        let data;
        try { data = JSON.parse(event.data); } catch { return; }
        if (!data || typeof data.tipo !== 'string' ||
            (data.id_vehiculo != null && data.id_vehiculo !== vehicleId)) return;
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
  accesoComprador(api, role, content, onConnect) {
    const token = sessionStorage.getItem(buyerKey);
    const volver = () => location.replace('./mis-vehiculos.html');
    if (!token || !Number.isSafeInteger(vehicleId) || vehicleId <= 0) {
      volver();
      return;
    }
    const status = document.querySelector('#status');
    const notice = document.querySelector('#notice');
    const connectivity = new Connectivity(api, vehicleId);
    const swagger = document.querySelector('[data-swagger]');
    if (swagger) swagger.href = new URL('/docs', config.api);
    api.token = token;
    let activo = true, intento = 0, timer;
    const reintentar = () => {
      if (!activo) return;
      clearTimeout(timer);
      content.hidden = true;
      status.textContent = 'Reconectando…';
      status.dataset.state = 'pending';
      timer = setTimeout(conectar, Math.min(15000, 750 * 2 ** Math.min(intento++, 5)));
    };
    const conectar = async () => {
      try {
        await api.get('/vehiculos/' + vehicleId + '/dispositivo');
        if (!activo) return;
        await api.open(token, role);
        await onConnect();
        if (!activo || !api.socket) return;
        intento = 0;
        content.hidden = false;
        notice.textContent = '';
        status.textContent = 'Conectado · Unidad ' + vehicleId;
        status.dataset.state = 'ready';
        void connectivity.check();
      } catch (err) {
        if (!activo) return;
        api.close();
        if (err.status === 401 || err.status === 403) {
          if (err.status === 401) sessionStorage.removeItem(buyerKey);
          activo = false;
          volver();
          return;
        }
        notice.textContent = err.message;
        reintentar();
      }
    };
    api.addEventListener('disconnect', reintentar);
    document.querySelector('#logout').onclick = async () => {
      activo = false;
      clearTimeout(timer);
      content.hidden = true;
      api.close();
      try {
        await api.request('/comercial/sesion', { method: 'DELETE' });
        sessionStorage.removeItem(buyerKey);
        volver();
      } catch (err) {
        notice.textContent = 'No se pudo confirmar la salida. ' + err.message;
        activo = true;
        reintentar();
      }
    };
    window.addEventListener('pagehide', () => { activo = false; clearTimeout(timer); api.close(); });
    window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
    void conectar();
  }

  constructor(api, role, content, onConnect = async () => {}) {
    const form = document.querySelector('#login');
    if (config.comercial && !personal) {
      form.hidden = true;
      location.replace('./mis-vehiculos.html');
      return;
    }
    if (personal) {
      form.hidden = true;
      this.accesoComprador(api, role, content, onConnect);
      return;
    }
    const formPosition = document.createComment('Acceso');
    const input = document.querySelector('#token');
    const remember = document.querySelector('#remember-code');
    const submit = form.querySelector('button[type="submit"]');
    const reveal = form.querySelector('.login-reveal');
    const status = document.querySelector('#status');
    const notice = document.querySelector('#notice');
    const connectivity = new Connectivity(api, vehicleId);
    let reconnectTimer;
    let accessVersion = 0;
    let attempts = 0;
    let resume = false;
    const retry = () => {
      clearTimeout(reconnectTimer);
      if (!resume || !input.value) return;
      setStatus('Reconectando…', 'pending');
      reconnectTimer = setTimeout(() => void connect(), Math.min(15000, 750 * 2 ** Math.min(attempts++, 5)));
    };
    const setStatus = (text, state) => {
      status.textContent = text;
      status.dataset.state = state;
      if (state !== 'ready') connectivity.socket(text, state);
    };
    const swagger = document.querySelector('[data-swagger]');
    if (swagger) swagger.href = new URL('/docs', config.api);
    const showCode = visible => {
      input.type = visible ? 'text' : 'password';
      reveal.setAttribute('aria-pressed', String(visible));
      reveal.textContent = visible ? 'Ocultar' : 'Mostrar';
    };
    reveal.addEventListener('click', () => showCode(input.type === 'password'));
    const connect = async (enteredByUser = false) => {
      if (submit.disabled || !form.checkValidity()) return;
      clearTimeout(reconnectTimer);
      submit.disabled = true;
      showCode(false);
      notice.textContent = '';
      setStatus('Conectando…', 'pending');
      const code = input.value;
      const version = accessVersion;
      try {
        await api.open(code, role);
        await onConnect();
        if (version !== accessVersion) return;
        if (!api.socket) throw new Error('Se cerró la conexión con la API.');
        attempts = 0;
        resume = true;
        saveCode('sessionStorage', code);
        if (!saveCode('localStorage', remember.checked ? code : '') && remember.checked) {
          remember.checked = false;
          notice.textContent = 'El navegador no pudo recordar el código.';
        }
        if (enteredByUser) {
          input.value = code;
          offerPasswordSave(form.elements.username.value, code);
        }
        form.replaceWith(formPosition);
        content.hidden = false;
        void connectivity.check();
        setStatus('Conectado', 'ready');
        connectivity.socket('En línea', 'ready');
      } catch (error) {
        if (version !== accessVersion) return;
        api.close();
        notice.textContent = error.message;
        setStatus('Sin conexión', 'offline');
      } finally {
        submit.disabled = false;
        if (!api.socket && resume) retry();
      }
    };
    api.addEventListener('disconnect', () => {
      setStatus('Sin conexión', 'offline');
      if (role !== 'iot-monitor' || !resume) {
        content.hidden = true;
        formPosition.replaceWith(form);
      }
      retry();
    });
    form.addEventListener('submit', event => { event.preventDefault(); void connect(true); });
    remember.addEventListener('change', () => { if (!remember.checked) saveCode('localStorage', ''); });
    document.querySelector('#logout').addEventListener('click', () => {
      accessVersion++;
      resume = false;
      content.hidden = true;
      formPosition.replaceWith(form);
      api.token = '';
      setStatus('Sin conexión', 'offline');
      clearTimeout(reconnectTimer);
      saveCode('sessionStorage', '');
      saveCode('localStorage', '');
      remember.checked = false;
      input.value = '';
      showCode(false);
      api.close();
    });
    window.addEventListener('pagehide', () => { resume = false; clearTimeout(reconnectTimer); });
    window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
    const saved = readCode('localStorage');
    remember.checked = Boolean(saved);
    submit.disabled = false;
    const remembered = readCode('sessionStorage') || saved;
    if (remembered) {
      input.value = remembered;
      void connect();
    }
  }
}
