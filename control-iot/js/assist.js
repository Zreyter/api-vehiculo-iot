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
    const { codigo, duracion_ms, pausa_ms = 150 } = step || {};
    if (!movementCodes.has(codigo) || !Number.isInteger(duracion_ms) || duracion_ms < 100 ||
        duracion_ms > 1000 || !Number.isInteger(pausa_ms) || pausa_ms < 100 || pausa_ms > 1000) {
      throw new Error('El plan contiene un movimiento o duración fuera del contrato.');
    }
    total += duracion_ms + pausa_ms;
    return { codigo, duracion_ms, pausa_ms };
  });
  if (total > 8000) throw new Error('La secuencia supera ocho segundos.');
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
      return 0;
    }
    const dx = x * 2 - 1;
    const dy = y * 2 - 1;
    if (Math.hypot(dx, dy) <= .28) this.centered = true;
    return this.centered ? direction(dx, dy, vehicleDirections, .6) : 0;
  }
}

/** Abre y libera la cámara. El modelo se inyecta como detect(video). */
export class CameraGestureInput {
  constructor({ video, detect, press, release }) {
    Object.assign(this, { video, detect, press, release });
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
      await this.video.play();
      if (generation === this.generation) void this.sample(stream);
    } catch (error) {
      if (generation !== this.generation) return;
      this.stop();
      throw error;
    } finally { this.starting = false; }
  }

  async sample(stream) {
    if (this.stream !== stream) return;
    if (document.hidden) return this.stop();
    let timer;
    try {
      const frame = await Promise.race([
        this.detect(this.video),
        new Promise(resolve => { timer = setTimeout(() => resolve(detectorTimeout), 250); }),
      ]);
      if (this.stream !== stream) return;
      if (frame === detectorTimeout) return this.stop();
      const code = this.gesture.update(frame);
      if (this.code !== code) {
        this.release('camera');
        this.code = code;
        if (code) this.press(code, 'camera');
      }
      requestAnimationFrame(() => this.sample(stream));
    } catch { this.stop(); }
    finally { clearTimeout(timer); }
  }

  stop() {
    this.generation++;
    this.visibility?.abort();
    this.release('camera');
    for (const track of this.stream?.getTracks() || []) track.stop();
    this.stream = this.video.srcObject = null;
    this.gesture.update(null);
    this.code = 0;
  }
}
