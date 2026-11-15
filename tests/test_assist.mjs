import assert from 'node:assert/strict';
import test from 'node:test';
import { CameraGestureInput, executeVoicePlan, PalmGesture, validateVoicePlan } from '../control-iot/js/assist.js';
import { AssistPanel } from '../control-iot/js/assist-panel.js';
import { KiwiListener } from '../control-iot/js/voice.js';

const step = { codigo: 2, duracion_ms: 100, pausa_ms: 100 };

test('la mano solo conduce después de pasar por el centro con la palma abierta', () => {
  const gesture = new PalmGesture();
  const palm = (x, y) => gesture.update({ gesture: 'Open_Palm', x, y });
  assert.equal(palm(.95, .5), 0);
  assert.equal(palm(.5, .5), 0);
  assert.equal(palm(.7, .5), 0);
  assert.equal(palm(.73, .5), 13);
  assert.equal(palm(.7, .5), 13);
  assert.equal(palm(.65, .5), 0);
  assert.equal(palm(.7, .5), 0);
  assert.equal(palm(.5, .5), 0);
  assert.equal(palm(.5, .1), 2);
  assert.equal(gesture.update(null), 0);
  assert.equal(palm(.5, .1), 0);
});

test('las pequeñas oscilaciones en diagonal no cambian la dirección', () => {
  const gesture = new PalmGesture();
  const palm = (x, y) => gesture.update({ gesture: 'Open_Palm', x, y });
  assert.equal(palm(.5, .5), 0);
  assert.equal(palm(.75, .5), 13);
  assert.equal(palm(.71, .27), 13);
  assert.equal(palm(.70, .24), 2);
  assert.equal(palm(.73, .29), 2);
  assert.equal(palm(.60, .40), 0);
});

test('el índice centrado controla la pala y el cambio de gesto libera el movimiento', () => {
  const gesture = new PalmGesture();
  const hand = (mode, x, y) => gesture.update({ gesture: mode, x, y });
  assert.equal(hand('Open_Palm', .5, .5), 0);
  assert.equal(hand('Open_Palm', .5, .1), 2);
  assert.equal(hand('Pointing_Up', .5, .1), 0);
  for (const [x, y, code] of [[.26, .5, 1], [.74, .5, 4], [.5, .26, 11], [.5, .74, 12]]) {
    assert.equal(hand('Pointing_Up', .5, .5), 0);
    assert.equal(hand('Pointing_Up', x, y), code);
  }
  assert.equal(hand('Closed_Fist', .5, .9), 0);
  assert.equal(hand('Pointing_Up', .5, .9), 0);
});

test('la pala responde a un gesto lateral más corto y tolera pequeñas diagonales', () => {
  const gesture = new PalmGesture();
  const hand = (x, y = .5) => gesture.update({ gesture: 'Pointing_Up', x, y });
  assert.equal(hand(.68), 0);
  assert.equal(hand(.5), 0);
  assert.equal(hand(.65), 0);
  assert.equal(hand(.68), 4);
  assert.equal(hand(.63), 4);
  assert.equal(hand(.68, .29), 4);
  assert.equal(hand(.60), 0);
  assert.equal(hand(.32), 1);
  assert.equal(gesture.update(null), 0);
  assert.equal(hand(.32), 0);
});

test('un video congelado o un detector lento sueltan la pala y conservan la cámara', t => {
  t.mock.method(performance, 'now', () => now);
  const originalDocument = globalThis.document;
  const originalFrame = globalThis.requestAnimationFrame;
  let nextFrame;
  globalThis.document = { hidden: false, hasFocus: () => focused };
  globalThis.requestAnimationFrame = run => { nextFrame = run; };
  let now = 0;
  let focused = true;
  let latency = 0;
  const hands = [[{ x: .5, y: .5 }]];
  let position = { gesture: 'Pointing_Up', x: .5, y: .5, hands };
  let overlay;
  const events = [];
  const video = { readyState: 2, currentTime: 0 };
  const camera = new CameraGestureInput({
    video,
    detect: () => { now += latency; return position; },
    press: code => { events.push(code); return true; },
    release: () => events.push(0),
    ended: assert.fail,
    draw: points => { overlay = points; },
    status() {},
  });
  const stream = camera.stream = {};
  camera.lastFrameAt = camera.nextSampleAt = now;
  const frame = (elapsed, newFrame = true) => {
    now += elapsed;
    if (newFrame) video.currentTime++;
    nextFrame();
  };
  try {
    camera.sample(stream);
    assert.equal(overlay, hands);
    position = { ...position, x: .1 };
    frame(65);
    assert.equal(events.at(-1), 1);
    frame(250, false);
    assert.equal(events.at(-1), 0);
    assert.deepEqual(overlay, []);
    assert.equal(camera.stream, stream);
    frame(65);
    assert.equal(events.at(-1), 0);
    position = { ...position, x: .5 };
    frame(65);
    position = { ...position, x: .1 };
    frame(65);
    assert.equal(events.at(-1), 1);
    latency = 250;
    frame(65);
    assert.equal(events.at(-1), 0);
    assert.equal(camera.stream, stream);
    latency = 0;
    frame(65);
    assert.equal(events.at(-1), 0);
    position = { ...position, x: .5 };
    frame(65);
    position = { ...position, x: .1 };
    frame(65);
    assert.equal(events.at(-1), 1);
    focused = false;
    frame(65);
    assert.equal(events.at(-1), 0);
    assert.equal(camera.stream, stream);
  } finally {
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
    if (originalFrame === undefined) delete globalThis.requestAnimationFrame;
    else globalThis.requestAnimationFrame = originalFrame;
  }
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

test('Kiwi ejecuta desde el panel y Parar descarta respuestas tardías', async () => {
  const elements = new Map();
  const originalDocument = globalThis.document;
  const originalWindow = globalThis.window;
  const { Speech, sessions } = mockSpeech();
  globalThis.window = { SpeechRecognition: Speech };
  globalThis.document = {
    hidden: false,
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, { setAttribute() {} });
      return elements.get(id);
    },
  };
  const calls = [];
  const reflected = [];
  let resolvePlan;
  let finish;
  const released = new Promise(resolve => { finish = resolve; });
  const drive = {
    hasControlConnection: () => true,
    canUseAssist: () => true,
    commands: new Map([[step.codigo, 1], [11, 2]]),
    api: {
      post(path, body, signal) {
        calls.push([path, body.frase, signal, body.codigos_anteriores]);
        return new Promise(resolve => { resolvePlan = resolve; });
      },
    },
    send(code, options) {
      assert.equal(options.stillWanted(), true);
      calls.push([code, options.duration]);
      return { recibida: true, orden_enviada: false };
    },
    show() {},
    reflectAssistMovement: code => reflected.push(code),
    release() { calls.push(['release']); finish(); },
    stop() { calls.push(['stop']); panel.cancel(); },
  };
  let panel;
  try {
    panel = new AssistPanel(drive);
    panel.camera.stop = () => {};
    elements.get('listen-voice').onclick();
    assert.equal(sessions[0].aborted, undefined);
    assert.equal(elements.get('kiwi-status').textContent, 'Kiwi activo');
    sessions[0].say('Kiwi, avanza');
    sessions[0].say('Kiwi, ignorar');
    resolvePlan({ pasos: [step, { ...step, codigo: 11 }] });
    await released;
    await Promise.resolve();
    assert.deepEqual(calls.map(call => call.slice(0, 2)), [
      ['/ia/plan', 'avanza'], [2, 100], [0, undefined], [11, 100], [0, undefined], ['release'],
    ]);
    assert.deepEqual(reflected, [2, 0, 11, 0, 0]);
    const second = panel.execute('avanza otra vez');
    const signal = calls.at(-1)[2];
    assert.deepEqual(calls.at(-1)[3], [2, 11]);
    sessions[0].say('Kiwi, para');
    resolvePlan({ pasos: [step] });
    await second;
    assert.equal(sessions[0].aborted, true);
    assert.equal(elements.get('kiwi-status').textContent, '');
    assert.equal(signal.aborted, true);
    assert.equal(calls.length, 8);
    assert.deepEqual(calls.at(-1), ['stop']);
    assert.equal(reflected.at(-1), 0);
  } finally {
    panel?.stopListening();
    if (originalWindow === undefined) delete globalThis.window;
    else globalThis.window = originalWindow;
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
  }
});

test('la cámara etiqueta los movimientos y refleja ambos joysticks', () => {
  const badge = { dataset: {}, textContent: '' };
  const previousDocument = globalThis.document;
  const buttons = { setAttribute() {} };
  globalThis.document = {
    getElementById(id) {
      if (id === 'gesture-movement') return badge;
      return buttons;
    },
  };
  const actions = [
    { code: 2, name: 'Avanzar', arrow: '↑' },
    { code: 4, name: 'Pala derecha', arrow: '→' },
  ];
  const state = { active: 0, pending: true, pulse: null };
  const reflected = [];
  const drive = {
    controller: { snapshot: () => state },
    hasControlConnection: () => true,
    canUseAssist: () => false,
    cameraOrder: null,
    reflectAssistMovement: code => reflected.push(code),
    stop: assert.fail,
  };
  const panel = new AssistPanel(drive, actions);
  const camera = panel.camera;
  camera.code = 2;
  const stream = camera.stream = {};
  const render = () => panel.renderCameraMovement();
  try {
    panel.render();
    assert.equal(camera.stream, stream);
    assert.equal(badge.textContent, 'Enviando · ↑ Avanzar');
    state.active = 2;
    state.pending = false;
    drive.cameraOrder = { codigo: 2, orden_enviada: false };
    render();
    assert.equal(badge.textContent, 'Sin envío · ↑ Avanzar');
    assert.equal(badge.dataset.active, 'false');

    camera.code = state.active = state.pulse = 4;
    drive.cameraOrder = { codigo: 4, orden_enviada: true };
    render();
    assert.equal(badge.textContent, 'Enviado · → Pala derecha');
    assert.equal(badge.dataset.active, 'true');

    state.pulse = null;
    state.active = 0;
    render();
    assert.equal(badge.textContent, 'Sin movimiento');
    assert.deepEqual(reflected, [0, 2, 4, 0]);
  } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
});
