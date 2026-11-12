/** Convierte el sector dominante de un vector en una sola orden. */
export function direction(x, y, codes, deadzone = .26) {
  if (!Number.isFinite(x) || !Number.isFinite(y) || Math.hypot(x, y) <= deadzone) return 0;
  if (Math.abs(x) > Math.abs(y)) return x < 0 ? codes.left : codes.right;
  return y < 0 ? codes.up : codes.down;
}

/** Pointer capture conserva la liberación al salir del círculo o cancelar el toque. */
export class Joystick {
  constructor(element, codes, input) {
    this.element = element;
    this.codes = codes;
    this.input = input;
    this.knob = element.querySelector('.knob');
    const offsets = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
    this.offsets = new Map(Object.entries(codes).map(([name, code]) => [code, offsets[name]]));
    element.addEventListener('pointerdown', event => {
      if (this.pointer != null || event.button !== 0 || !input.enabled()) return;
      this.pointer = event.pointerId;
      element.setPointerCapture(this.pointer);
      this.move(event);
    });
    element.addEventListener('pointermove', event => {
      if (event.pointerId === this.pointer) this.move(event);
    });
    for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      element.addEventListener(name, event => { if (event.pointerId === this.pointer) this.clear(); });
    }
  }

  move(event) {
    const box = this.element.getBoundingClientRect();
    const radius = box.width / 2;
    const x = (event.clientX - box.left - radius) / radius;
    const y = (event.clientY - box.top - radius) / radius;
    this.position(x, y, radius);
    const code = direction(x, y, this.codes);
    if (code !== this.code) {
      this.input.release(this.element.id);
      this.code = code;
      if (code) this.input.press(code, this.element.id);
    }
  }

  position(x, y, radius) {
    const scale = radius * .66 / Math.max(1, Math.hypot(x, y));
    this.knob.style.setProperty('--stick-x', `${x * scale}px`);
    this.knob.style.setProperty('--stick-y', `${y * scale}px`);
  }

  showInput(commands) {
    this.inputCode = commands.find(code => this.offsets.has(code));
    if (this.pointer == null) this.showDirection();
  }

  showDirection() {
    const [x, y] = this.offsets.get(this.inputCode) ?? [0, 0];
    this.position(x, y, this.element.getBoundingClientRect().width / 2);
  }

  clear() {
    this.pointer = null;
    this.code = 0;
    this.showDirection();
    this.input.release(this.element.id);
  }
}

export const vehicleDirections = Object.freeze({ up: 2, left: 10, down: 3, right: 13 });
export const bucketDirections = Object.freeze({ up: 11, left: 1, down: 12, right: 4 });
