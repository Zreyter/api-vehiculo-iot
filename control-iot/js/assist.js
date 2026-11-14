import { direction, vehicleDirections } from './joystick.js';

const movementCodes = new Set([1, 2, 3, 4, 10, 11, 12, 13]);
const detectorTimeout = Symbol('detectorTimeout');

/** El proveedor de voz entrega datos; el controlador conserva la autoridad sobre los movimientos. */
export function validateVoicePlan(plan) {
  if (!Array.isArray(plan?.pasos) || !plan.pasos.length || plan.pasos.length > 8) {
    throw new Error('La secuencia debe contener de uno a ocho pasos.');
  }
  let total = 0;
  const pasos = plan.pasos.map(step => {
    const { codigo, duracion_ms, pausa_ms } = step || {};
    if (!movementCodes.has(codigo) || !Number.isInteger(duracion_ms) || duracion_ms < 100 ||
        duracion_ms > 5000 ||
        !Number.isInteger(pausa_ms) || pausa_ms < 100 || pausa_ms > 1000) {
      throw new Error('El plan contiene un movimiento o duración fuera del contrato.');
    }
    total += duracion_ms + pausa_ms;
    return { codigo, duracion_ms, pausa_ms };
  });
  if (total > 30000) throw new Error('La secuencia supera 30 segundos.');
  return pasos;
}

/**
 * El proveedor de visión devuelve {abierta, x, y}, en coordenadas 0–1 del
 * video visible. Para arrancar exige palma abierta en el centro.
 */
export class PalmGesture {
  update(sample) {
    const { abierta, x, y } = sample || {};
    if (!abierta || !Number.isFinite(x) || !Number.isFinite(y) || x < 0 || x > 1 || y < 0 || y > 1) {
      this.centered = false;
      this.previous = 0;
      return 0;
    }
    const dx = x * 2 - 1;
    const dy = y * 2 - 1;
    if (Math.hypot(dx, dy) <= .28) this.centered = true;
    const code = this.centered ? direction(dx, dy, vehicleDirections, .6) : 0;
    if (this.previous && !code) this.centered = Math.hypot(dx, dy) <= .28;
    this.previous = code;
    return code;
  }
}

/** Abre y libera la cámara. El modelo se inyecta como detect(video). */
export class CameraGestureInput {
  constructor({ video, detect, press, release, ended }) {
    Object.assign(this, { video, detect, press, release, ended });
    this.gesture = new PalmGesture();
    this.generation = 0;
  }

  async start() {
    if (this.stream || this.starting || document.hidden) return;
    const generation = ++this.generation;
    this.starting = true;
    this.visibility = new AbortController();
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) this.stop();
    }, { signal: this.visibility.signal });
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
      if (generation !== this.generation || document.hidden) {
        for (const track of stream.getTracks()) track.stop();
        if (generation === this.generation) this.stop();
        return;
      }
      this.video.srcObject = this.stream = stream;
      for (const track of stream.getVideoTracks()) {
        track.addEventListener('ended', () => this.stop('La cámara se desconectó.'), { signal: this.visibility.signal });
      }
      await this.video.play();
      if (generation === this.generation) {
        this.lastVideoTime = -1;
        this.lastFrameAt = performance.now();
        return true;
      }
    } catch (error) {
      if (generation !== this.generation) return;
      this.stop();
      throw error;
    } finally { this.starting = false; }
  }

  async sample(stream) {
    if (this.stream !== stream) return;
    if (document.hidden) return this.stop();
    const start = performance.now();
    if (start - this.lastFrameAt > 250) return this.stop('Se interrumpió el video de la cámara.');
    if (this.video.currentTime === this.lastVideoTime || start - this.lastFrameAt < 65 ||
        this.video.readyState < 2) {
      this.frame = requestAnimationFrame(() => this.sample(stream));
      return;
    }
    this.lastVideoTime = this.video.currentTime;
    this.lastFrameAt = start;
    let timer;
    try {
      const frame = await Promise.race([
        this.detect(this.video),
        new Promise(resolve => { timer = setTimeout(() => resolve(detectorTimeout), 250); }),
      ]);
      if (this.stream !== stream) return;
      if (frame === detectorTimeout || performance.now() - start >= 250) {
        return this.stop('El seguimiento de la mano se interrumpió.');
      }
      const code = this.gesture.update(frame);
      if (this.code !== code) {
        this.release('camera');
        this.code = code;
        if (code) this.press(code, 'camera');
      }
      this.frame = requestAnimationFrame(() => this.sample(stream));
    } catch { this.stop('No se pudo seguir la mano.'); }
    finally { clearTimeout(timer); }
  }

  stop(message) {
    this.generation++;
    this.visibility?.abort();
    cancelAnimationFrame(this.frame);
    this.release('camera');
    for (const track of this.stream?.getTracks() || []) track.stop();
    this.stream = this.video.srcObject = null;
    this.gesture.update(null);
    this.code = 0;
    if (message) this.ended(message);
  }
}

const visionAssets = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21';
const palmModel = 'https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task';

export async function createPalmDetector() {
  const { FilesetResolver, GestureRecognizer } = await import(visionAssets + '/vision_bundle.mjs');
  const vision = await FilesetResolver.forVisionTasks(visionAssets + '/wasm');
  const recognizer = await GestureRecognizer.createFromOptions(vision, {
    baseOptions: { modelAssetPath: palmModel },
    runningMode: 'VIDEO',
    numHands: 2,
  });
  return {
    close: () => recognizer.close(),
    detect(video) {
      const { gestures, landmarks } = recognizer.recognizeForVideo(video, performance.now());
      const gesture = gestures[0]?.[0];
      if (landmarks.length !== 1 || gesture?.categoryName !== 'Open_Palm' || gesture.score < .65) return null;
      const palm = [0, 5, 9, 13, 17].map(index => landmarks[0][index]);
      return {
        abierta: true,
        x: 1 - palm.reduce((sum, point) => sum + point.x, 0) / palm.length,
        y: palm.reduce((sum, point) => sum + point.y, 0) / palm.length,
      };
    },
  };
}

function delay(ms, signal) {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort);
      resolve();
    }, ms);
    function abort() {
      clearTimeout(timer);
      reject(signal.reason);
    }
    signal.addEventListener('abort', abort, { once: true });
  });
}

export async function executeVoicePlan(plan, { send, signal, onStep = () => {} }) {
  const steps = validateVoicePlan(plan);
  let sent = 0;
  for (const [index, step] of steps.entries()) {
    signal.throwIfAborted();
    onStep(index + 1, steps.length);
    const order = await send(step.codigo, step.duracion_ms);
    if (order.cancelado || !(order.recibida || order.orden_enviada || order.salidas_confirmadas)) {
      throw new Error(order.mensaje || 'La API no procesó el movimiento.');
    }
    if (order.orden_enviada || order.salidas_confirmadas) sent++;
    await delay(step.duracion_ms, signal);
    const stop = await send(0);
    if (stop.cancelado || !(stop.recibida || stop.orden_enviada || stop.salidas_confirmadas)) {
      throw new Error(stop.mensaje || 'La API no procesó la liberación.');
    }
    await delay(step.pausa_ms, signal);
  }
  return { sent, total: steps.length };
}
