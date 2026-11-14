import { CameraGestureInput, createPalmDetector, executeVoicePlan, validateVoicePlan } from './assist.js';
import { KiwiListener } from './voice.js';

const $ = id => document.getElementById(id);

export class AssistPanel {
  constructor(drive) {
    this.drive = drive;
    this.dialog = $('assist-settings');
    this.phrase = $('voice-phrase');
    this.camera = new CameraGestureInput({
      video: $('gesture-video'),
      detect: video => this.detector.detect(video),
      press: (code, source) => drive.press(code, source),
      release: source => drive.releaseInput(source),
      ended: message => { this.show(message); void drive.stop(); },
    });
    $('voice-control').onclick = () => this.select('voice');
    $('gesture-control').onclick = () => this.select('gesture');
    $('listen-voice').onclick = () => this.toggleListening();
    $('voice-form').onsubmit = event => {
      event.preventDefault();
      void this.execute(this.phrase.value.trim());
    };
    $('start-camera').onclick = () => this.startCamera();
    $('stop-assist').onclick = () => { this.show('Control con IA detenido.'); void drive.stop(); };
    this.dialog.addEventListener('close', () => {
      if (this.running || this.camera.stream || drive.controller.snapshot().armed) void drive.stop();
      else this.cancel();
    });
  }

  show(message) { $('assist-notice').textContent = message; }

  render() {
    const cameraActive = Boolean(this.camera.stream || this.cameraRequest);
    const available = this.drive.canUseAssist();
    $('voice-control').disabled = $('gesture-control').disabled = Boolean(this.running || cameraActive);
    this.phrase.disabled = Boolean(this.running);
    $('send-voice').disabled = Boolean(this.running || !available);
    const listen = $('listen-voice');
    listen.disabled = !this.listener && Boolean(this.running || !available);
    listen.textContent = this.listener ? 'Apagar micrófono' : 'Activar «Kiwi»';
    $('start-camera').disabled = cameraActive || Boolean(this.running) || !available;
    $('stop-assist').disabled = !cameraActive && !this.running && !this.listener;
  }

  select(mode) {
    this.cancel();
    this.show('');
    for (const name of ['voice', 'gesture']) {
      $(name + '-options').hidden = mode !== name;
      $(name + '-control').setAttribute('aria-expanded', String(mode === name));
    }
  }

  micStatus(message) { $('voice-status').textContent = message; }

  toggleListening() {
    if (this.listener) {
      this.stopListening();
      this.micStatus('Micrófono apagado.');
      this.render();
      return;
    }
    if (!this.drive.canUseAssist() || this.running) return;
    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Speech) return this.show('Este navegador no ofrece reconocimiento de voz. Puedes escribir la orden.');
    this.show('');
    this.micStatus('Activando micrófono…');
    const listener = this.listener = new KiwiListener({
      Speech,
      onStatus: message => this.micStatus(message),
      onCommand: phrase => void this.execute(phrase),
      onStop: () => { this.show('Control por voz detenido.'); void this.drive.stop(); },
      onError: message => {
        this.listener = null;
        this.micStatus(message);
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
    this.micStatus('');
  }

  async execute(frase) {
    if (!frase || this.running || !this.drive.canUseAssist()) return;
    if (frase.length > this.phrase.maxLength) {
      this.show('La orden es demasiado larga. Intenta con una frase más corta.');
      return;
    }
    this.listener?.resetWake();
    const run = this.running = new AbortController();
    this.render();
    this.show('Interpretando la orden…');
    let movementRequested = false;
    try {
      const plan = await this.drive.api.post('/ia/plan', { frase }, run.signal);
      if (this.running !== run || !this.drive.canUseAssist()) return;
      const pasos = validateVoicePlan(plan);
      if (!pasos.every(step => this.drive.commands.has(step.codigo))) {
        throw new Error('La orden incluye movimientos que no están disponibles.');
      }
      this.show('Ejecutando la orden…');
      const { sent, total } = await executeVoicePlan({ pasos }, {
        signal: run.signal,
        send: (code, duration) => {
          if (code !== 0) movementRequested = true;
          return this.drive.send(code, {
            duration,
            stillWanted: () => this.dialog.open && !run.signal.aborted && !document.hidden,
          });
        },
      });
      if (this.running === run) this.show(`Orden completada. Envíos a la placa: ${sent} de ${total}.`);
    } catch (error) {
      if (this.running === run) this.show(error.message);
    } finally {
      if (this.running === run) {
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
    if (!this.drive.canUseAssist() || this.cameraRequest || this.camera.stream) return;
    if (!navigator.mediaDevices?.getUserMedia) return this.show('La cámara requiere HTTPS o localhost.');
    const request = this.cameraRequest = new AbortController();
    this.render();
    this.show('Cargando el detector de manos…');
    try {
      const detector = await createPalmDetector();
      if (request.signal.aborted) { detector.close(); return; }
      this.detector = detector;
      this.show('Autoriza el acceso a la cámara.');
      const ready = await this.camera.start();
      if (request.signal.aborted) return;
      if (!ready || !this.drive.canUseAssist() || !this.drive.activate()) {
        throw new Error('No se pudo activar el control por cámara.');
      }
      $('gesture-preview').hidden = false;
      this.show('Cámara activa.');
      void this.camera.sample(this.camera.stream);
    } catch (error) {
      if (!request.signal.aborted) {
        this.cancel();
        this.show(error.name === 'NotAllowedError' ? 'Permite el acceso a la cámara.' :
          'No se pudo iniciar la cámara o cargar el detector de manos.');
      }
    } finally {
      if (this.cameraRequest === request) this.cameraRequest = null;
      this.render();
    }
  }

  cancel() {
    this.running?.abort();
    this.running = null;
    this.stopListening();
    this.cameraRequest?.abort();
    this.cameraRequest = null;
    this.camera.stop();
    this.detector?.close();
    this.detector = null;
    $('gesture-preview').hidden = true;
    this.render();
  }
}
