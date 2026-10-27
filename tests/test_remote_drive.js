'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function fixture() {
  const calls=[],suspensions=[],timers=new Map(),pending=[];
  let now=0,id=0;
  const bridge={sendDrive:async()=>{},releaseOnExit(){},snapshot:()=>({connected:false})};
  const window={vehiclePanel:bridge,panelDrive:{isArmed:()=>true,suspend:reason=>suspensions.push(reason)},
    addEventListener(){},dispatchEvent(){}};
  const context={window,$:()=>({value:'wifi',addEventListener(){}}),Event:class{},queueMicrotask,
    document:{hidden:false,hasFocus:()=>true},performance:{now:()=>now},
    setInterval:(callback,ms)=>{timers.set(++id,{callback,ms});return id;},clearInterval:key=>timers.delete(key),
    api:async(method,url,body,options)=>{
      calls.push({method,url,body,options});
      if(method==='POST')return {lease_id:'a'.repeat(32)};
      if(method==='DELETE')return {salidas_confirmadas:true};
      if(method==='PUT')return new Promise((resolve,reject)=>pending.push({resolve,reject}));
    }};
  vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../app/panel/remote-drive.js'),'utf8'),context);
  const target=()=>({transport:'wifi',vehicle:1,token:'test-only',generation:1});
  const tick=time=>{now=time;return [...timers.values()].find(t=>t.ms===200).callback();};
  return {bridge,remote:window.RemoteDrive,calls,suspensions,pending,target,tick};
}

test('renovaciones pueden continuar mientras una respuesta anterior tarda',async()=>{
  const s=fixture(),target=s.target();await s.bridge.prepareDrive(target);
  const first=s.tick(200),second=s.tick(400);
  assert.equal(s.pending.length,2);
  s.pending.forEach(p=>p.resolve({vence_en_ms:900}));await Promise.all([first,second]);
  assert.equal(s.suspensions.length,0);
});

test('respuesta fallida de una sesión terminada no suspende al controlador nuevo',async()=>{
  const s=fixture(),old=s.target();await s.bridge.prepareDrive(old);
  const first=s.tick(200);await s.remote.release(old);
  await s.bridge.prepareDrive(s.target());
  s.pending[0].reject(new Error('HTTP 409'));await first;
  assert.equal(s.suspensions.length,0);
});

test('no se acumulan renovaciones ni se reanuda sin confirmaciones',async()=>{
  const s=fixture();await s.bridge.prepareDrive(s.target());
  const first=s.tick(200),second=s.tick(400);await s.tick(600);await s.tick(800);
  assert.equal(s.pending.length,2);assert.equal(s.suspensions.length,1);
  s.pending.forEach(p=>p.resolve({vence_en_ms:900}));await Promise.all([first,second]);
});

test('renovación vigente fallida conserva la pausa',async()=>{
  const s=fixture();await s.bridge.prepareDrive(s.target());
  const tick=s.tick(200);s.pending[0].reject(new Error('HTTP 409'));await tick;
  assert.equal(s.suspensions.length,1);
});

test('renovaciones tienen un plazo propio y no se aceptan respuestas antiguas',async()=>{
  const s=fixture();await s.bridge.prepareDrive(s.target());
  const first=s.tick(200);
  assert.equal(s.calls.at(-1).options.timeoutMs,600);
  s.tick(900);s.pending[0].resolve({vence_en_ms:900});await first;
  assert.ok(s.suspensions.length>=1);
});
