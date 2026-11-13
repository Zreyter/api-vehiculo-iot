import assert from 'node:assert/strict';
import test from 'node:test';
import { executeVoicePlan, PalmGesture, validateVoicePlan } from '../control-iot/js/assist.js';

const step = { codigo: 2, duracion_ms: 100, pausa_ms: 100 };

test('la mano solo conduce después de pasar por el centro con la palma abierta', () => {
  const gesture = new PalmGesture();
  const palm = (x, y) => gesture.update({ abierta: true, x, y });
  assert.equal(palm(.95, .5), 0);
  assert.equal(palm(.5, .5), 0);
  assert.equal(palm(.95, .5), 13);
  assert.equal(palm(.7, .5), 0);
  assert.equal(palm(.95, .5), 0);
  assert.equal(palm(.5, .5), 0);
  assert.equal(palm(.5, .1), 2);
  assert.equal(gesture.update(null), 0);
  assert.equal(palm(.5, .1), 0);
});

test('se rechazan códigos de función, booleanos, pulsos inválidos y secuencias largas', () => {
  assert.deepEqual(validateVoicePlan({ pasos: [step] }), [step]);
  for (const codigo of [0, 4, 9, 14, true]) {
    assert.throws(() => validateVoicePlan({ pasos: [{ ...step, codigo }] }));
  }
  const long = { ...step, duracion_ms: 1000, pausa_ms: 1000 };
  assert.throws(() => validateVoicePlan({ pasos: Array(5).fill(long) }));
});

test('la ejecución libera salidas entre pasos y conserva la duración solicitada', async () => {
  const calls = [];
  await executeVoicePlan({ pasos: [step, { ...step, codigo: 3 }] }, {
    signal: new AbortController().signal,
    onStep() {},
    send(...order) { calls.push(order); return { orden_enviada: true, sesion_activa: true }; },
  });
  assert.deepEqual(calls, [[2, 100], [0], [3, 100], [0]]);
});

test('una secuencia continúa si la API recibe las órdenes sin placa', async () => {
  const calls = [];
  const summary = await executeVoicePlan({ pasos: [step, step] }, {
    signal: new AbortController().signal,
    onStep() {},
    send(code) {
      calls.push(code);
      return { recibida: true, orden_enviada: false, sesion_activa: false };
    },
  });
  assert.deepEqual(calls, [2, 0, 2, 0]);
  assert.deepEqual(summary, { sent: 0, total: 2 });
});

test('una cancelación o una orden que la API no acepta impiden pasos posteriores', async () => {
  for (const cancel of [true, false]) {
    const run = new AbortController();
    const calls = [];
    await assert.rejects(executeVoicePlan({ pasos: [step, step] }, {
      signal: run.signal,
      onStep() {},
      send(code) {
        calls.push(code);
        if (cancel) run.abort();
        return { orden_enviada: cancel, sesion_activa: cancel };
      },
    }));
    assert.deepEqual(calls, [2]);
  }
});
