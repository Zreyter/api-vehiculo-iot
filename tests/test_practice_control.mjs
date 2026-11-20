import test from 'node:test';
import assert from 'node:assert/strict';
import { PracticeControl } from '../control-iot/js/practice-control.js';

function setup(post) {
  globalThis.VehicleDrive = { actions: [{ code: 2, name: 'Avanzar' }] };
  const api = Object.assign(new EventTarget(), { post });
  const receipt = {};
  const practice = new PracticeControl(api, receipt, 1);
  practice.enabled = true;
  practice.commands = new Map([[2, 102], [0, 105]]);
  return { practice, receipt, api };
}

test('una parada pendiente conserva su indicador aunque la respuesta anterior llegue tarde', async () => {
  let finishMove;
  const sent = [];
  const { practice, receipt, api } = setup(async (path, body) => {
    assert.equal(path, '/vehiculos/1/movimientos');
    sent.push(body.id_comando);
    if (body.id_comando === 102) await new Promise(resolve => { finishMove = resolve; });
    const event = { tipo: 'movimiento_individual', id_vehiculo: 1, id_comando: body.id_comando,
      marca_temporal: '2026-11-20T15:00:00Z' };
    api.dispatchEvent(new CustomEvent('vehicle', { detail: event }));
    return event;
  });
  const moving = practice.move(2, {});
  await Promise.resolve();
  const stop = practice.move(0, {});
  assert.match(receipt.textContent, /Detener · Solicitado/);
  finishMove();
  await Promise.all([moving, stop]);
  assert.deepEqual(sent, [102, 105]);
  assert.match(receipt.textContent, /Detener · Aceptado por API .*Evento WSS recibido/);
});

test('modo registro identifica su demo aunque la API devuelva id_ejecucion nulo', async () => {
  const event = { tipo: 'demo_iniciada', id_vehiculo: 1, id_demo: 42,
    id_ejecucion: null, marca_temporal: '2026-11-20T15:00:01Z' };
  const { practice, api, receipt } = setup(async () => event);
  await practice.startDemo(42);
  assert.match(receipt.textContent, /Esperando evento WSS/);
  api.dispatchEvent(new CustomEvent('vehicle', { detail: { ...event, id_vehiculo: 2 } }));
  assert.match(receipt.textContent, /Esperando evento WSS/);
  assert.equal(practice.isCurrentDemo({ ...event, marca_temporal: '2026-11-20T15:00:00Z' }), false);
  assert.equal(practice.isCurrentDemo({ ...event, id_demo: 43 }), false);
  assert.equal(practice.isCurrentDemo({ ...event, tipo: 'demo_cancelada' }), true);
});
