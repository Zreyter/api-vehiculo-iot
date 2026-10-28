const {test}=require('node:test');
const assert=require('node:assert/strict');
const {DemoControl}=require('../app/panel/demo-control.js');

function setup() {
  let tick, connected=true, calls=[],lost=0;
  const control=new DemoControl({
    renew:async(v,id)=>{calls.push([v,id]);},
    connected:()=>connected,
    lost:()=>lost++,
    every:fn=>{tick=fn;return 1;},clear:()=>{}
  });
  return {control,calls,tick:()=>tick(), disconnect:()=>{connected=false;},lost:()=>lost};
}
const event={tipo:'demo_iniciada',modo_demo:'fisico',id_ejecucion:'a'.repeat(32)};
test('only the initiating page renews the returned execution identity',async()=>{
  const x=setup();x.control.start(event,'1');await Promise.resolve();await x.tick();
  assert.deepEqual(x.calls, [['1',event.id_ejecucion],['1',event.id_ejecucion]]);
});
test('loss of events channel stops heartbeats permanently',async()=>{
  const x=setup();x.control.start(event,'1');await Promise.resolve();x.disconnect();await x.tick();await x.tick();
  assert.equal(x.calls.length,1);assert.equal(x.lost(),1);assert.equal(x.control.run,null);
});
test('a failed renewal stops retries and requests a fresh start',async()=>{
  const x=setup();x.control.renew=async()=>{throw Error('network');};
  x.control.start(event,'1');await new Promise(setImmediate);
  assert.equal(x.lost(),1);assert.equal(x.control.run,null);
});
test('terminal event before HTTP response cannot restart completed sequence',()=>{
  const x=setup();x.control.event({...event,tipo:'demo_finalizada'});assert.equal(x.control.start(event,'1'),false);
  assert.equal(x.calls.length,0);assert.equal(x.control.run,null);
});
test('events from other sequences do not terminate current heartbeat',()=>{
  const x=setup();x.control.start(event,'1');
  x.control.event({...event,tipo:'error',id_ejecucion:'b'.repeat(32)});
  assert.equal(x.control.run.id,event.id_ejecucion);
  x.control.event({...event,tipo:'demo_cancelada'});assert.equal(x.control.run,null);
});
test('closing or changing vehicle stops renewal; observers never start it',async()=>{
  const x=setup();x.control.event(event);assert.equal(x.control.run,null);
  x.control.start(event,'1');await Promise.resolve();x.control.stop();await x.tick();
  assert.equal(x.calls.length,1);
});
test('a pending request cannot create overlapping heartbeat requests',async()=>{
  const x=setup();let complete;x.control.renew=()=>new Promise(resolve=>{complete=resolve;});
  x.control.start(event,'1');const run=x.control.run;await x.tick();
  assert.equal(run.busy,true);complete();await Promise.resolve();assert.equal(run.busy,false);
});
