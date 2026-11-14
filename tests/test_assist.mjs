import assert from 'node:assert/strict';
import test from 'node:test';
import { executeVoicePlan, PalmGesture, validateVoicePlan } from '../control-iot/js/assist.js';
import { AssistPanel } from '../control-iot/js/assist-panel.js';
import { KiwiListener } from '../control-iot/js/voice.js';

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
  for (const codigo of [0, 9, 14, true]) {
    assert.throws(() => validateVoicePlan({ pasos: [{ ...step, codigo }] }));
  }
  const long = { ...step, codigo: 4, duracion_ms: 5000, pausa_ms: 1000 };
  assert.deepEqual(validateVoicePlan({ pasos: Array(5).fill(long) }), Array(5).fill(long));
  assert.throws(() => validateVoicePlan({ pasos: Array(6).fill(long) }));
  assert.throws(() => validateVoicePlan({ pasos: [{ ...long, duracion_ms: 5001 }] }));
});

test('la ejecución libera salidas entre pasos y conserva la duración solicitada', async () => {
  const calls = [];
  await executeVoicePlan({ pasos: [step, { ...step, codigo: 4, duracion_ms: 250 }] }, {
    signal: new AbortController().signal,
    onStep() {},
    send(...order) { calls.push(order); return { orden_enviada: true, sesion_activa: true }; },
  });
  assert.deepEqual(calls, [[2, 100], [0], [4, 250], [0]]);
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

function mockSpeech() {
  const sessions = [];
  class Speech {
    start() { sessions.push(this); this.onstart(); }
    abort() { this.aborted = true; this.onend(); }
    say(transcript, isFinal = true) {
      this.onresult({ resultIndex: 0, results: [{ 0: { transcript }, isFinal }] });
    }
  }
  return { Speech, sessions };
}

test('Kiwi acepta una frase completa o una orden después de una pausa', () => {
  const { Speech, sessions } = mockSpeech();
  const commands = [];
  let stops = 0;
  let status;
  const listener = new KiwiListener({
    Speech,
    onStatus: value => { status = value; },
    onCommand: value => commands.push(value),
    onStop: () => { stops++; },
    onError: assert.fail,
  });
  listener.start();
  try {
    const speech = sessions[0];
    assert.equal(speech.continuous, true);
    speech.say('saluda con la pala');
    speech.say('kiwito, avanza');
    speech.say('Kiwi, saluda', false);
    assert.deepEqual(commands, []);
    speech.say('¡Kiwi, saluda con la pala!');
    speech.say('Kiwi.');
    assert.equal(status, 'Te escucho…');
    speech.say('Gira la pala a la derecha');
    speech.say('retrocede');
    speech.say('Kiwi, para por favor.');
    assert.deepEqual(commands, ['saluda con la pala', 'Gira la pala a la derecha']);
    assert.equal(stops, 1);
  } finally {
    listener.stop();
  }
  assert.equal(sessions[0].aborted, true);
  sessions[0].say('Kiwi, avanza');
  assert.equal(commands.length, 2);
});

test('el micrófono se rearma cuando el navegador termina un ciclo de escucha', async () => {
  const { Speech, sessions } = mockSpeech();
  const commands = [];
  const listener = new KiwiListener({
    Speech,
    onStatus() {},
    onCommand: value => commands.push(value),
    onStop: assert.fail,
    onError: assert.fail,
  });
  listener.start();
  try {
    sessions[0].say('Kiwi');
    sessions[0].onend();
    await new Promise(resolve => setTimeout(resolve, 350));
    assert.equal(sessions.length, 2);
    sessions[1].say('saluda');
    assert.deepEqual(commands, ['saluda']);
  } finally {
    listener.stop();
  }
});

test('una orden se planifica y ejecuta una sola vez y Parar descarta respuestas tardías', async () => {
  const elements = new Map();
  const originalDocument = globalThis.document;
  globalThis.document = {
    hidden: false,
    getElementById(id) {
      if (!elements.has(id)) {
        elements.set(id, { open: true, maxLength: 240, addEventListener() {} });
      }
      return elements.get(id);
    },
  };
  const calls = [];
  let resolvePlan;
  const drive = {
    canUseAssist: () => true,
    commands: new Map([[step.codigo, 1]]),
    api: {
      post(path, body, signal) {
        calls.push([path, body.frase, signal]);
        return new Promise(resolve => { resolvePlan = resolve; });
      },
    },
    send(code, options) {
      calls.push([code, options.duration]);
      return { recibida: true, orden_enviada: false };
    },
    release() { calls.push(['release']); },
  };
  try {
    const panel = new AssistPanel(drive);
    panel.camera.stop = () => {};
    const first = panel.execute('avanza');
    await panel.execute('ignorar');
    resolvePlan({ pasos: [step] });
    await first;
    assert.deepEqual(calls.map(call => call.slice(0, 2)), [
      ['/ia/plan', 'avanza'], [2, 100], [0, undefined], ['release'],
    ]);
    const second = panel.execute('avanza otra vez');
    const signal = calls.at(-1)[2];
    panel.cancel();
    resolvePlan({ pasos: [step] });
    await second;
    assert.equal(signal.aborted, true);
    assert.equal(calls.length, 5);
  } finally {
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
  }
});
