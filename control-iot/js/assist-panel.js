import { CameraGestureInput, createPalmDetector, executeVoicePlan, validateVoicePlan } from './assist.js';

const $ = id => document.getElementById(id);

export class AssistPanel {
  constructor(drive, actions) {
    this.drive = drive;
    this.actions = actions;
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
    $('listen-voice').onclick = () => this.listen();
    $('voice-form').onsubmit = event => { event.preventDefault(); void this.prepare(); };
    $('execute-voice').onclick = () => this.execute();
    $('start-camera').onclick = () => this.startCamera();
    $('stop-assist').onclick = () => { this.show('Control con IA detenido.'); void drive.stop(); };
    this.phrase.oninput = () => { this.clearPlan(); this.show(''); };
    this.dialog.addEventListener('close', () => {
      if (this.running || this.camera.stream || drive.controller.snapshot().armed) void drive.stop();
      else this.cancel();
    });
  }

  show(message) { $('assist-notice').textContent = message; }

  render() {
    const active = Boolean(this.running || this.camera.stream || this.cameraRequest);
    $('voice-control').disabled = $('gesture-control').disabled = active;
    this.phrase.disabled = Boolean(this.running);
    $('plan-voice').disabled = Boolean(this.running || this.recognition || this.planRequest);
    $('listen-voice').disabled = Boolean(this.running || this.recognition || this.planRequest);
    $('start-camera').disabled = active || !this.drive.canUseAssist();
    $('stop-assist').disabled = !active && !this.recognition && !this.planRequest;
    $('execute-voice').disabled = Boolean(this.running || !this.drive.canUseAssist());
  }

  select(mode) {
    this.cancel();
    this.show('');
    for (const name of ['voice', 'gesture']) {
      $(name + '-options').hidden = mode !== name;
      $(name + '-control').setAttribute('aria-expanded', String(mode === name));
    }
  }

  clearPlan() {
    this.planRequest?.abort();
    this.planRequest = this.plan = null;
    $('voice-plan').replaceChildren();
    $('voice-plan').hidden = $('execute-voice').hidden = true;
    this.render();
  }

  listen() {
    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Speech) return this.show('Este navegador no ofrece dictado. Escribe la orden para continuar.');
    this.clearPlan();
    const recognition = this.recognition = new Speech();
    recognition.lang = 'es-MX';
    recognition.onresult = event => {
      if (this.recognition !== recognition) return;
      this.phrase.value = event.results[0][0].transcript.trim().slice(0, this.phrase.maxLength);
      this.show('Revisa la frase y pulsa Preparar plan.');
    };
    recognition.onerror = () => {
      if (this.recognition === recognition) this.show('No se pudo transcribir el audio. Puedes escribir la orden.');
    };
    recognition.onend = () => {
      if (this.recognition === recognition) this.recognition = null;
      this.render();
    };
    try {
      recognition.start();
      this.show('Habla ahora.');
    } catch {
      this.recognition = null;
      this.show('No se pudo iniciar el micrófono.');
    }
    this.render();
  }

  async prepare() {
    const frase = this.phrase.value.trim();
    if (!frase) return this.show('Escribe o dicta una orden.');
    this.clearPlan();
    const request = this.planRequest = new AbortController();
    this.render();
    this.show('Interpretando la orden…');
    try {
      const plan = await this.drive.api.post('/ia/plan', { frase }, request.signal);
      if (this.planRequest !== request || !this.dialog.open) return;
      this.plan = validateVoicePlan(plan);
      $('voice-plan').replaceChildren(...this.plan.map(step => {
        const item = document.createElement('li');
        const name = this.actions.find(action => action.code === step.codigo).name;
        item.textContent = name + ' · ' + step.duracion_ms + ' ms, pausa ' + step.pausa_ms + ' ms';
        return item;
      }));
      $('voice-plan').hidden = $('execute-voice').hidden = false;
      this.show('Revisa los movimientos antes de ejecutar el plan.');
    } catch (error) {
      if (this.planRequest === request) this.show(error.message);
    } finally {
      if (this.planRequest === request) this.planRequest = null;
      this.render();
    }
  }

  async execute() {
    if (!this.plan || this.running || !this.drive.canUseAssist()) return;
    const plan = { pasos: this.plan };
    if (!plan.pasos.every(step => this.drive.commands.has(step.codigo))) {
      return this.show('El catálogo tiene movimientos del plan que no están disponibles.');
    }
    this.clearPlan();
    const run = this.running = new AbortController();
    this.render();
    try {
      const { sent, total } = await executeVoicePlan(plan, {
        signal: run.signal,
        send: (code, duration) => this.drive.send(code, {
          duration,
          stillWanted: () => this.dialog.open && !run.signal.aborted && !document.hidden,
        }),
        onStep: (step, count) => this.show(`Procesando paso ${step} de ${count}…`),
      });
      if (this.running === run) this.show(`Plan completado. Envíos a la placa: ${sent} de ${total}.`);
    } catch (error) {
      if (this.running === run) this.show(error.message);
    } finally {
      if (this.running === run) {
        this.running = null;
        await this.drive.stop();
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
    const recognition = this.recognition;
    this.recognition = null;
    recognition?.abort();
    this.cameraRequest?.abort();
    this.cameraRequest = null;
    this.camera.stop();
    this.detector?.close();
    this.detector = null;
    $('gesture-preview').hidden = true;
    this.clearPlan();
  }
}
