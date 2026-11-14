import { CameraGestureInput, createPalmDetector, executeVoicePlan, validateVoicePlan } from './assist.js';
import { KiwiListener } from './voice.js';

const $ = id => document.getElementById(id);
const maxVoicePhraseLength = 240;

export class AssistPanel {
  constructor(drive, actions = []) {
    this.drive = drive;
    this.actions = actions;
    this.camera = new CameraGestureInput({
      video: $('gesture-video'),
      detect: video => this.detector.detect(video),
      draw: hands => this.detector?.draw($('gesture-video'), hands),
      press: (code, source) => drive.press(code, source),
      release: source => drive.releaseInput(source),
      ended: message => { this.show(message); void drive.stop(); },
      status: message => {
        const status = $('gesture-status');
        if (status.textContent !== message) status.textContent = message;
        this.renderCameraMovement();
      },
    });
    $('listen-voice').onclick = () => this.toggleListening();
    $('start-camera').onclick = () => {
      if (this.camera.stream || this.cameraRequest) {
        this.show('Cámara apagada.');
        void drive.stop();
      } else {
        void this.startCamera();
      }
    };
  }

  show(message) { this.drive.show(message); }

  get cameraActive() { return Boolean(this.camera.stream || this.cameraRequest); }

  render() {
    const cameraActive = this.cameraActive;
    const voiceActive = Boolean(this.listener || this.running);
    const connected = this.drive.hasControlConnection();
    const available = connected && this.drive.canUseAssist();
    const camera = $('start-camera');
    camera.hidden = !connected;
    camera.setAttribute('aria-pressed', String(cameraActive));
    camera.disabled = !cameraActive && (voiceActive || !available);
    const kiwi = $('listen-voice');
    kiwi.hidden = !connected;
    kiwi.setAttribute('aria-pressed', String(voiceActive));
    kiwi.disabled = !voiceActive && (cameraActive || !available);
    if (this.camera.stream) this.renderCameraMovement();
  }

  renderCameraMovement() {
    const badge = $('gesture-movement');
    const code = this.camera.code;
    const action = this.actions.find(item => item.code === code);
    const state = this.drive.controller.snapshot();
    const active = action && state.active === code && (code !== 4 || state.pulse === code);
    const result = this.drive.cameraOrder;
    let label = 'Sin movimiento';
    if (active && result?.codigo === code) {
      const status = result.orden_enviada ? 'Enviado' : result.salidas_confirmadas ? 'Confirmado' : 'Sin envío';
      label = `${status} · ${action.arrow} ${action.name}`;
    } else if (action && state.pending && !active) {
      label = `Enviando · ${action.arrow} ${action.name}`;
    }
    if (badge.textContent !== label) badge.textContent = label;
    const sent = String(Boolean(active && (result?.orden_enviada || result?.salidas_confirmadas)));
    if (badge.dataset.active !== sent) badge.dataset.active = sent;
    this.drive.reflectAssistMovement(active ? code : 0);
  }

  micStatus() {
    $('kiwi-status').textContent = this.listener
      ? (this.listener.waiting ? 'Kiwi · Te escucho…' : 'Kiwi activo')
      : '';
  }

  toggleListening() {
    if (this.listener || this.running) {
      this.show('Kiwi desactivado.');
      void this.drive.stop();
      return;
    }
    if (!this.drive.canUseAssist() || this.cameraActive) return;
    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Speech) return this.show('Este navegador no ofrece reconocimiento de voz.');
    this.show('Di «Kiwi» y tu orden. Para detenerte, di «Kiwi, para».');
    const listener = this.listener = new KiwiListener({
      Speech,
      onStatus: () => this.micStatus(),
      onCommand: phrase => {
        if (!this.running && !this.drive.canUseAssist()) {
          this.show('Suelta el control manual o termina la demo antes de usar Kiwi.');
          return;
        }
        void this.execute(phrase);
      },
      onStop: () => { this.show('Control por voz detenido.'); void this.drive.stop(); },
      onError: message => {
        this.listener = null;
        this.micStatus();
        this.show(message);
        this.render();
      },
    });
    listener.start();
    this.render();
  }

  stopListening() {
    const listener = this.listener;
    this.listener = null;
    listener?.stop();
    this.micStatus();
  }

  async execute(frase) {
    if (!frase || this.running || !this.drive.canUseAssist()) return;
    if (frase.length > maxVoicePhraseLength) {
      this.show('La orden es demasiado larga. Intenta con una frase más corta.');
      return;
    }
    this.listener?.resetWake();
    const run = this.running = new AbortController();
    this.render();
    this.show('Interpretando la orden…');
    let movementRequested = false;
    try {
      const plan = await this.drive.api.post('/ia/plan', {
        frase, codigos_anteriores: this.lastVoiceCodes,
      }, run.signal);
      if (this.running !== run || !this.drive.canUseAssist()) return;
      const pasos = validateVoicePlan(plan);
      if (!pasos.every(step => this.drive.commands.has(step.codigo))) {
        throw new Error('La orden incluye movimientos que no están disponibles.');
      }
      this.lastVoiceCodes = pasos.map(step => step.codigo);
      this.show('Ejecutando la orden…');
      const { sent, total } = await executeVoicePlan({ pasos }, {
        signal: run.signal,
        send: async (code, duration) => {
          if (code === 0) this.drive.reflectAssistMovement(0);
          else movementRequested = true;
          const result = await this.drive.send(code, {
            duration,
            stillWanted: () => !run.signal.aborted && this.drive.canUseAssist(),
          });
          if (code && this.running === run && !result.cancelado &&
              (result.recibida || result.orden_enviada || result.salidas_confirmadas)) {
            this.drive.reflectAssistMovement(code);
          }
          return result;
        },
      });
      if (this.running === run) this.show(`Orden completada. Envíos a la placa: ${sent} de ${total}.`);
    } catch (error) {
      if (this.running === run) this.show(error.message);
    } finally {
      if (this.running === run) {
        this.drive.reflectAssistMovement(0);
        try {
          if (movementRequested) await this.drive.release();
        } finally {
          if (this.running === run) this.running = null;
          this.render();
        }
      }
    }
  }

  async startCamera() {
    if (!this.drive.canUseAssist() || this.cameraActive || this.listener || this.running) return;
    if (!navigator.mediaDevices?.getUserMedia) return this.show('La cámara requiere HTTPS o localhost.');
    const request = this.cameraRequest = new AbortController();
    this.render();
    this.show('Cargando el detector de manos…');
    try {
      const detector = await createPalmDetector($('gesture-landmarks'));
      if (request.signal.aborted) { detector.close(); return; }
      this.detector = detector;
      this.show('Autoriza el acceso a la cámara.');
      const ready = await this.camera.start();
      if (request.signal.aborted) return;
      if (!ready || !this.drive.canUseAssist() || !this.drive.activate('camera')) {
        throw new Error('No se pudo activar el control por cámara.');
      }
      $('gesture-card').hidden = false;
      $('gesture-help').hidden = false;
      this.show('');
      void this.camera.sample(this.camera.stream);
    } catch (error) {
      if (!request.signal.aborted) {
        this.cancel();
        this.show(error.name === 'NotAllowedError' ? 'Permite el acceso a la cámara.' :
          'No se pudo iniciar la cámara o cargar el detector de manos.');
      }
    } finally {
      if (this.cameraRequest === request) this.cameraRequest = null;
      this.drive.render();
    }
  }

  cancel() {
    this.running?.abort();
    this.running = null;
    this.stopListening();
    this.cameraRequest?.abort();
    this.cameraRequest = null;
    this.camera.stop();
    this.drive.cameraOrder = null;
    this.drive.reflectAssistMovement(0);
    this.detector?.close();
    this.detector = null;
    $('gesture-help').hidden = true;
    $('gesture-card').hidden = true;
    this.render();
  }
}
