'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {actions,resolveCommands,gamepadInputs,createController} = require('../app/panel/drive-controller.js');
function setup(sendOverride) {
  const sent=[], timers=new Map(), errors=[];
  let timerId=0;
  const send=async(code,target)=>{sent.push({code,target});if(sendOverride)await sendOverride(code,target);};
  const control=createController({send, fault:(e,stopFailed)=>errors.push({e,stopFailed}),
    timer:(fn,ms)=>{const id=++timerId;timers.set(id,{fn,ms});return id;}, cancel:id=>timers.delete(id)});
  const target={vehicle:1,token:'test-only',generation:1,commands:new Map(actions.map(a=>[a.code,100+a.code]))};
  const fire=()=>{const [id,t]=timers.entries().next().value;timers.delete(id);t.fn();};
  control.arm(target);
  return {control,sent,timers,errors,target,fire,codes:()=>sent.map(s=>s.code)};
}

test('registro ocupado libera, mantiene la sesión y exige otra pulsación',async()=>{
  const sent=[],notices=[];
  const controller=createController({send:async code=>{
    sent.push(code);return code===10?{codigo:0,cancelado:true,registro_ocupado:true,salidas_confirmadas:true,mensaje:'Guardando'}:{};
  },notice:message=>notices.push(message)});
  controller.arm({vehicle:1,transport:'wifi',commands:new Map(actions.map(a=>[a.code,a.code]))});
  controller.press(10,'left');await controller.idle();
  assert.equal(controller.snapshot().active,0);assert.equal(controller.snapshot().armed,true);
  assert.equal(controller.snapshot().confirmed,true);assert.equal(notices.at(-1),'Guardando');
  await controller.idle();assert.deepEqual(sent,[10]);
  controller.release('left');controller.press(2,'forward');await controller.idle();
  assert.deepEqual(sent,[10,2]);
});

test('prueba de liberación de sesión finalizada pausa sin nueva activación',async()=>{
  const controller=createController({send:async()=>({codigo:0,sesion_finalizada:true,salidas_confirmadas:true})});
  controller.arm({vehicle:1,transport:'wifi',commands:new Map([[0,0],[2,2]])});
  await controller.halt();assert.equal(controller.snapshot().armed,false);
  assert.equal(controller.snapshot().active,0);assert.equal(controller.snapshot().stopFailed,false);
  assert.equal(controller.press(2,'W'),false);
});

test('joystick izquierdo no repite pulsaciones por ruido junto a la zona muerta',()=>{
  let inputs=gamepadInputs({buttons:[],axes:[-.35,0]},.25);
  assert.ok(inputs.has('a0-'));
  for(const value of [-.299,-.301,-.295,-.305]){
    inputs=gamepadInputs({buttons:[],axes:[value,0]},.25,inputs);
    assert.ok(inputs.has('a0-'));
  }
  inputs=gamepadInputs({buttons:[],axes:[-.24,0]},.25,inputs);
  assert.equal(inputs.size,0);
});
test('catálogo se resuelve por código, sin confundirlo con el ID',()=>{
  const result=resolveCommands([{codigo:'2',id_comando:87,activo:1},{codigo:0,id_comando:92,activo:1},{codigo:5,id_comando:90,activo:0}]);
  assert.equal(result.map.get(2),87);assert.equal(result.map.get(0),92);assert.ok(result.missing.includes(5));
  assert.deepEqual(resolveCommands([{codigo:2,id_comando:1,activo:1},{codigo:2,id_comando:2,activo:1}]).ambiguous,[2]);
});
test('una tecla mantenida no repite y se libera con código 0',async()=>{
  const s=setup();s.control.press(2,'W');await s.control.idle();s.control.press(2,'W');await s.control.idle();
  s.control.release('W');await s.control.idle();assert.deepEqual(s.codes(),[2,0]);
});
test('prioridad de la última entrada y recuperación de la anterior',async()=>{
  const s=setup();s.control.press(2,'W');await s.control.idle();s.control.press(10,'A');await s.control.idle();
  s.control.release('A');await s.control.idle();s.control.release('W');await s.control.idle();assert.deepEqual(s.codes(),[2,10,2,0]);
});
test('soltar una entrada secundaria no libera la que sigue activa',async()=>{
  const s=setup();s.control.press(2,'keyboard');await s.control.idle();s.control.press(10,'pad');await s.control.idle();
  s.control.release('keyboard');await s.control.idle();assert.deepEqual(s.codes(),[2,10]);
  s.control.release('pad');await s.control.idle();assert.deepEqual(s.codes(),[2,10,0]);
});
test('liberación durante una escritura lenta no se pierde ni acumula órdenes viejas',async()=>{
  let unblock;const pending=new Promise(r=>unblock=r);const s=setup(code=>code===2?pending:undefined);
  s.control.press(2,'W');await Promise.resolve();await Promise.resolve();
  s.control.press(10,'A');s.control.release('A');s.control.release('W');unblock();await s.control.idle();assert.deepEqual(s.codes(),[2,0]);
});
test('un pulso de 200 ms no se corta al soltar ni se repite mientras se mantiene',async()=>{
  const s=setup();s.control.press(5,'Z');await s.control.idle();assert.equal([...s.timers.values()][0].ms,200);
  s.control.release('Z');await s.control.idle();assert.deepEqual(s.codes(),[5]);
  assert.equal(s.control.press(6,'X'),false);s.fire();await s.control.idle();assert.deepEqual(s.codes(),[5,0]);
  s.control.press(5,'Z');await s.control.idle();s.fire();await s.control.idle();s.control.press(5,'Z');await s.control.idle();
  assert.deepEqual(s.codes(),[5,0,5,0]);
});
test('encendido requiere estado supuesto y protege los 2 segundos de apagado',async()=>{
  const s=setup();assert.equal(s.control.press(9,'P'),false);
  await s.control.halt();s.control.setPower('on');s.control.arm(s.target);s.control.press(9,'P');await s.control.idle();
  assert.equal([...s.timers.values()][0].ms,2000);assert.equal(s.control.press(2,'W'),false);
  s.fire();await s.control.idle();assert.equal(s.control.snapshot().power,'off');
  s.control.release('P');s.control.press(9,'P');await s.control.idle();assert.equal([...s.timers.values()][0].ms,200);
  await s.control.halt();assert.equal(s.control.snapshot().power,'unknown');assert.equal(s.timers.size,0);
});
test('cambio de sección, foco o mando cancela todas las fuentes y exige reactivar',async()=>{
  const s=setup();s.control.press(2,'key');await s.control.idle();await s.control.halt('blur');
  assert.equal(s.control.press(10,'pad'),false);assert.deepEqual(s.codes(),[2,0]);assert.equal(s.control.snapshot().armed,false);
});
test('una liberación pendiente conserva el vehículo y el token anteriores',async()=>{
  let unblock;const pending=new Promise(r=>unblock=r);const s=setup(code=>code===2?pending:undefined);
  s.control.press(2,'W');await Promise.resolve();await Promise.resolve();
  const released=s.control.halt();const next={...s.target,vehicle:2,token:'other'};
  assert.equal(s.control.arm(next),false);unblock();await released;
  assert.deepEqual(s.sent.map(x=>x.target.vehicle),[1,1]);assert.equal(s.sent[1].target.token,'test-only');
  assert.equal(s.control.arm(next),true);
});
test('error de red desactiva entradas e intenta liberar',async()=>{
  const s=setup(code=>{if(code===2)throw Error('offline');});s.control.press(2,'W');await s.control.idle();
  assert.deepEqual(s.codes(),[2,0]);assert.equal(s.control.snapshot().armed,false);assert.equal(s.errors.length,1);
});
test('liberación fallida queda visible y se puede reintentar sin bucle',async()=>{
  let offline=true;const s=setup(()=>{if(offline)throw Error('offline');});s.control.press(2,'W');await s.control.idle();
  assert.deepEqual(s.codes(),[2,0]);assert.equal(s.control.snapshot().stopFailed,true);
  offline=false;await s.control.halt();assert.deepEqual(s.codes(),[2,0,0]);assert.equal(s.control.snapshot().stopFailed,false);
});
test('zona muerta, gatillos y direcciones del mando',()=>{
  const pad={axes:[.2,-.8,0,.7],buttons:[{pressed:false,value:0},{pressed:false,value:.8}]};
  assert.deepEqual([...gamepadInputs(pad,.25)],['b1','a1-','a3+']);
  assert.deepEqual([...gamepadInputs({axes:[.25,-.25],buttons:[]},.25)],[]);
});
test('no se activa sin una liberación disponible',()=>{
  const c=createController({send:async()=>{}});assert.equal(c.arm({commands:new Map([[2,102]])}),false);
});
test('un pulso remoto respeta la duración confirmada por la placa',async()=>{
  const timers=[];
  const c=createController({send:async()=>({duracion_ms:2000}),timer:(fn,ms)=>{timers.push({fn,ms});return 1;},cancel:()=>{}});
  c.setPower('off');c.arm({commands:new Map([[0,100],[9,109]])});
  c.press(9,'P');await c.idle();assert.equal(timers[0].ms,2000);
  await c.halt();
});
test('el adaptador puede descartar una entrada soltada mientras se adquiría sesión',async()=>{
  let options,unblock;
  const pending=new Promise(resolve=>unblock=resolve);
  const c=createController({send:async(code,target,metadata)=>{if(code===2){options=metadata;await pending;}}});
  c.arm({commands:new Map([[0,100],[2,102]])});c.press(2,'W');await Promise.resolve();await Promise.resolve();
  assert.equal(options.stillWanted(),true);c.release('W');assert.equal(options.stillWanted(),false);unblock();await c.idle();
});

test('WiFi envía liberar antes de recibir el ACK de avance y descarta su respuesta tardía',async()=>{
  let finish;
  const s=setup(code=>code===2?new Promise(resolve=>finish=resolve):undefined);
  s.target.transport='wifi';s.control.press(2,'W');await Promise.resolve();await Promise.resolve();
  s.control.release('W');await Promise.resolve();await Promise.resolve();await Promise.resolve();
  assert.deepEqual(s.codes(),[2,0]);
  finish();await s.control.idle();assert.equal(s.control.snapshot().active,0);
  assert.equal(s.control.snapshot().confirmed,true);
});

test('la parada WiFi tiene prioridad y un error antiguo no vuelve a enviar la orden',async()=>{
  let fail;
  const s=setup(code=>code===2?new Promise((resolve,reject)=>fail=reject):undefined);
  s.target.transport='wifi';s.control.press(2,'W');await Promise.resolve();await Promise.resolve();
  const stopped=s.control.halt();await Promise.resolve();await Promise.resolve();
  assert.deepEqual(s.codes(),[2,0]);fail(Error('ACK antiguo perdido'));await stopped;
  assert.equal(s.control.snapshot().active,0);assert.equal(s.control.snapshot().armed,false);
  assert.deepEqual(s.errors,[]);
});
