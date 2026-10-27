/* Lógica de entradas compartida por el navegador y las pruebas de Node. */
(function (root) {
  'use strict';
  const actions = [
    {code:2, name:'Avanzar', group:'carro', key:'KeyW', pad:'a1-', held:true, arrow:'↑'},
    {code:10, name:'Carro izquierda', group:'carro', key:'KeyA', pad:'a0-', held:true, arrow:'←'},
    {code:3, name:'Retroceder', group:'carro', key:'KeyS', pad:'a1+', held:true, arrow:'↓'},
    {code:13, name:'Carro derecha', group:'carro', key:'KeyD', pad:'a0+', held:true, arrow:'→'},
    {code:11, name:'Agarrar pala', group:'pala', key:'ArrowUp', pad:'a3-', held:true, arrow:'↑'},
    {code:1, name:'Pala izquierda', group:'pala', key:'ArrowLeft', pad:'a2-', held:true, arrow:'←'},
    {code:12, name:'Soltar pala', group:'pala', key:'ArrowDown', pad:'a3+', held:true, arrow:'↓'},
    {code:4, name:'Pala derecha', group:'pala', key:'ArrowRight', pad:'a2+', held:true, arrow:'→'},
    {code:9, name:'Encender / apagar', group:'rapidas', key:'KeyP', pad:'b9', held:false, arrow:'⏻'},
    {code:5, name:'Mute', group:'rapidas', key:'KeyZ', pad:'b2', held:false, arrow:'♪'},
    {code:6, name:'Velocidad', group:'rapidas', key:'KeyX', pad:'b0', held:false, arrow:'↗'},
    {code:7, name:'Luces LED', group:'rapidas', key:'KeyC', pad:'b3', held:false, arrow:'☀'},
    {code:8, name:'DEMO del carro', group:'rapidas', key:'KeyV', pad:'b1', held:false, arrow:'▷'},
    {code:0, name:'Parar / liberar', group:'stop', key:'Space', pad:'b8', held:false, arrow:'■'},
  ];
  function resolveCommands(commands) {
    const map = new Map(), missing = [], ambiguous = [];
    for (const action of actions) {
      const matches = commands.filter(c => c.activo === 1 && String(c.codigo).trim() === String(action.code));
      if (matches.length === 1) map.set(action.code, matches[0].id_comando);
      else (matches.length ? ambiguous : missing).push(action.code);
    }
    return {map, missing, ambiguous};
  }
  function gamepadInputs(pad, deadzone = .25, previous = new Set()) {
    const inputs = new Set();
    (pad.buttons || []).forEach((b, i) => { if (b.pressed || b.value > .5) inputs.add('b' + i); });
    (pad.axes || []).forEach((v, i) => {
      const input='a' + i + (v < 0 ? '-' : '+');
      // La zona configurada siempre libera. Para entrar se exige un pequeño
      // margen adicional que evita nuevas pulsaciones por ruido del stick.
      const threshold=previous.has(input)?deadzone:deadzone+Math.min(.05,deadzone*.2);
      if (Math.abs(v) > threshold) inputs.add(input);
    });
    return inputs;
  }
  function createController({send, changed = () => {}, fault = () => {}, notice = () => {}, timer = setTimeout, cancel = clearTimeout}) {
    let armed = false, context = null, active = null, desired = null, pumping = null, confirmed = false;
    let pulse = null, pulseTimer = null, power = 'unknown', stopFailed = false;
    let sending = null, revision = 0, priority = null;
    const pressed = new Map();
    const snapshot = () => ({armed, active, confirmed, pending: !!pumping || !!priority, pulse: pulse?.code ?? null, power, stopFailed});
    const notify = () => changed(snapshot());
    const latest = () => Array.from(pressed.values()).filter(x => x.held).at(-1)?.code ?? 0;
    function clearPulse() {
      cancel(pulseTimer); pulseTimer = null;
      if (pulse?.code === 9) power = 'unknown';
      pulse = null;
    }
    function halt(reason = '') {
      armed = false; pressed.clear(); clearPulse();
      if (context) desired = 0;
      if (context?.transport === 'wifi' && sending !== null && sending !== 0) priorityStop();
      notify(); pump();
      return idle();
    }
    function priorityStop() {
      if (priority || !context) return;
      revision++;
      const target = context;
      priority = Promise.resolve().then(() => send(0, target, {priority:true})).then(receipt => {
        active = 0; confirmed = receipt?.cancelado !== true; stopFailed = false;
        if(receipt?.sesion_finalizada){armed=false;pressed.clear();clearPulse();desired=0;}
      }).catch(error => {
        armed = false; pressed.clear(); clearPulse(); active = null; desired = null;
        stopFailed = true; fault(error, true);
      }).finally(() => { priority = null; notify(); pump(); });
    }
    async function run() {
      while (desired !== null && desired !== active) {
        if (priority) { await priority; continue; }
        const code = desired, target = context, currentPulse = pulse, ticket = revision;
        sending = code;
        try {
          const receipt = await send(code, target, {stillWanted: () => armed && desired === code});
          if (ticket !== revision) continue;
          if(receipt?.registro_ocupado){
            pressed.clear();clearPulse();active=desired=0;confirmed=true;stopFailed=false;
            notice(receipt.mensaje);continue;
          }
          if(receipt?.sesion_finalizada){armed=false;pressed.clear();clearPulse();desired=0;}
          active = code; confirmed = receipt?.cancelado !== true; stopFailed = false;
          if (currentPulse && pulse === currentPulse && code === pulse.code) {
            pulseTimer = timer(() => {
              if (pulse !== currentPulse) return;
              if (code === 9) power = power === 'off' ? 'on' : 'off';
              pulse = null; pulseTimer = null;
              desired = armed ? latest() : 0;
              pump(); notify();
            }, receipt?.duracion_ms ?? currentPulse.duration);
          }
        } catch (error) {
          if (ticket !== revision) continue;
          armed = false; pressed.clear(); clearPulse();
          // Una escritura fallida puede haber llegado al servidor. Intentar liberar
          // con el mismo vehículo y token; nunca continuar con entradas acumuladas.
          active = null;
          desired = code === 0 ? null : 0;
          stopFailed = code === 0;
          fault(error, stopFailed);
        } finally {
          sending = null;
        }
        notify();
      }
    }
    function pump() {
      if (pumping) return;
      pumping = Promise.resolve().then(run).finally(() => {
        pumping = null; notify();
        if (desired !== null && desired !== active) pump();
      });
    }
    async function idle() { while (pumping || priority) await (pumping || priority); }
    return {
      snapshot, idle, halt, currentContext: () => context,
      setPower(value) { if (!armed && !pumping) { power = value; notify(); } },
      arm(target) {
        if (armed || pumping || priority || !target.commands.has(0)) return false;
        context = target; active = null; desired = null; stopFailed = false;
        pressed.clear(); armed = true; notify(); return true;
      },
      press(code, source) {
        if (code === 0) { halt('Parada'); return true; }
        const action = actions.find(a => a.code === code);
        if (!armed || pulse || !action || !context.commands.has(code) || pressed.has(source)) return false;
        if (code === 9 && power === 'unknown') return false;
        notice('');
        pressed.set(source, action);
        if (!action.held) pulse = {code, duration: code === 9 && power === 'on' ? 2000 : 200};
        desired = code; pump(); notify(); return true;
      },
      release(source) {
        const action = pressed.get(source);
        if (!action) return;
        pressed.delete(source);
        if (action.held && !pulse) {
          desired = latest();
          if (context?.transport === 'wifi' && desired === 0 && sending !== null && sending !== 0) priorityStop();
          pump();
        }
        notify();
      },
    };
  }
  const api = {actions, resolveCommands, gamepadInputs, createController};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.VehicleDrive = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
