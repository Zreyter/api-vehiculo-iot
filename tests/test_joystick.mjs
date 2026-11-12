import assert from 'node:assert/strict';
import test from 'node:test';
import { Joystick, vehicleDirections, bucketDirections } from '../control-iot/js/joystick.js';

test('los joysticks reflejan la última dirección y regresan al centro', () => {
  function createStick(codes) {
    const offsets = new Map();
    const element = Object.assign(new EventTarget(), {
      querySelector: () => ({ style: { setProperty: (key, value) => offsets.set(key, value) } }),
      getBoundingClientRect: () => ({ width: 200, left: 0, top: 0 }),
      setPointerCapture() {},
    });
    const stick = new Joystick(element, codes, { enabled: () => true, press() {}, release() {} });
    return {
      show: commands => stick.showInput(commands),
      position: () => [offsets.get('--stick-x'), offsets.get('--stick-y')],
      pointer: (type, x, y) => element.dispatchEvent(Object.assign(new Event(type), {
        pointerId: 1, button: 0, clientX: x, clientY: y,
      })),
    };
  }

  const vehicle = createStick(vehicleDirections);
  const bucket = createStick(bucketDirections);
  for (const stick of [vehicle, bucket]) stick.show([13, 2, 11]);
  assert.deepEqual(vehicle.position(), ['66px', '0px']);
  assert.deepEqual(bucket.position(), ['0px', '-66px']);

  vehicle.pointer('pointerdown', 0, 100);
  vehicle.show([3]);
  assert.deepEqual(vehicle.position(), ['-66px', '0px']);
  vehicle.pointer('pointerup', 0, 100);
  assert.deepEqual(vehicle.position(), ['0px', '66px']);

  for (const stick of [vehicle, bucket]) {
    stick.show([]);
    assert.deepEqual(stick.position(), ['0px', '0px']);
  }
});
