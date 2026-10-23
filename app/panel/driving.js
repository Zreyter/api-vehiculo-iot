'use strict';
(() => {
  const {actions, resolveCommands, gamepadInputs, createController} = window.VehicleDrive;
  const storageKey = 'vehiculo-iot.conduccion.v1';
  const keyText = code => ({Space:'Espacio', ArrowUp:'↑', ArrowDown:'↓', ArrowLeft:'←', ArrowRight:'→', Escape:'Esc'}[code] || code.replace(/^Key|^Digit/, ''));
  const buttonNames = ['A','B','X','Y','LB','RB','LT','RT','Vista / Back','Menú / Start','Stick izquierdo','Stick derecho','Cruceta ↑','Cruceta ↓','Cruceta ←','Cruceta →','Xbox'];
  const padOptions = [['','Sin asignar'], ...buttonNames.map((name,i) => ['b'+i,name]),
    ...['Izquierdo ←','Izquierdo →','Izquierdo ↑','Izquierdo ↓','Derecho ←','Derecho →','Derecho ↑','Derecho ↓'].map((name,i) => ['a'+Math.floor(i/2)+(i%2?'+':'-'),name])];
  const defaults = () => ({keys:Object.fromEntries(actions.map(a => [a.code,a.key])), pads:Object.fromEntries(actions.map(a => [a.code,a.pad])), deadzone:.25});
  const bindableKey = code => /^(Key[A-Z]|Digit[0-9]|Arrow(Up|Down|Left|Right)|Space|Backspace|Numpad([0-9]|Add|Subtract|Multiply|Divide|Decimal)|F([1-9]|1[0-2])|Minus|Equal|BracketLeft|BracketRight|Backslash|Semicolon|Quote|Backquote|Comma|Period|Slash|Home|End|PageUp|PageDown|Insert|Delete)$/.test(code);
  let preferences = defaults(), storageOK = true;
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
    if (saved) {
      const validKeys = new Set(), validPads = new Set();
      for (const a of actions) {
        const k = saved.keys?.[a.code], p = saved.pads?.[a.code];
        if (typeof k !== 'string' || (k && (!bindableKey(k) || validKeys.has(k)))) throw Error();
        if (!padOptions.some(([id]) => id === p) || (p && validPads.has(p))) throw Error();
        if (k) validKeys.add(k); if (p) validPads.add(p);
      }
      if (typeof saved.deadzone !== 'number' || saved.deadzone < .1 || saved.deadzone > .8) throw Error();
      preferences = saved;
    }
  } catch { storageOK = false; }
  let capture = null, padIndex = '', lastPadId = '', padDown = new Set(), padNeutral = false;
  let lastContext = '', lastCommands = '', lastAvailability = '', lastRender = '';
  let engineState, controller, padSignature = '';
  const inputDown = new Set();
  const panel = () => window.vehiclePanel.snapshot();
  const physical = () => !!window.RemoteDrive?.physical();
  function resolvedCommands(commands) {
    const result=resolveCommands(commands);
    if(physical()) { result.map.set(0,0); result.missing=result.missing.filter(c=>c!==0); }
    return result;
  }
  const targetSnapshot = p => ({vehicle:p.vehicle.id_vehiculo,token:p.token,generation:p.generation,
    commands:resolvedCommands(p.commands).map,transport:physical()?'wifi':'registro'});
  const onPage = () => panel().page === 'conduccion';
  const usable = () => { const p = panel(); return (!physical() || window.RemoteDrive.ready()) && onPage() && p.connected && p.vehicle?.activo === 1 && !p.running && !p.busy && p.socketOpen && !document.hidden && document.hasFocus() && !document.querySelector('dialog[open]'); };
  function save() {
    try { localStorage.setItem(storageKey, JSON.stringify(preferences)); storageOK = true; }
    catch { storageOK = false; }
    $('#driveStorage').textContent = storageOK ? 'Preferencias guardadas en este navegador.' : 'Las preferencias solo se conservarán mientras esta página esté abierta.';
  }
  function setMessage(message, error = false) {
    $('#driveFeedback').textContent = message;
    $('#driveFeedback').classList.toggle('error', error);
  }
  function clearInputs() { inputDown.clear(); padDown.clear(); padNeutral = false; }
  function suspend(reason) {
    const target=window.RemoteDrive?.target();
    capture = null; clearInputs();
    renderBindings();
    if (controller?.snapshot().armed) {
      setMessage(reason + ' Vuelve a activar la conducción para continuar.');
      return controller.halt(reason).then(()=>window.RemoteDrive?.release(target));
    }
    return controller?.idle().then(()=>window.RemoteDrive?.release(target));
  }
  controller = createController({
    send: (code, target, options) => window.vehiclePanel.sendDrive(code, target, options),
    changed: value => { engineState = value; renderStatus(); },
    fault: (error, stopFailed) => {
      clearInputs();
      setMessage(error.message + (stopFailed ? ' No se confirmó la liberación. Comprueba la conexión y pulsa Parar de nuevo.' : ' Se desactivó la conducción y se solicitó liberar.'), true);
    },
  });
  engineState = controller.snapshot();
  function controlButton(a) {
    return '<button type="button" class="drive-key" data-drive="'+a.code+'" aria-label="'+esc(a.name)+'" aria-pressed="false" disabled><span class="drive-symbol">'+a.arrow+'</span><strong>'+a.name+'</strong><span class="drive-shortcut" data-shortcut="'+a.code+'"></span><small>Código '+a.code+' · '+(a.held?'mantener':a.code===9?'200 ms / 2 s':'200 ms')+'</small></button>';
  }
  for (const group of ['carro','pala','rapidas']) $('#drive-'+group).innerHTML = actions.filter(a => a.group===group).map(controlButton).join('');
  $('#driveBindings').innerHTML = actions.map(a => '<tr><td><strong>'+esc(a.name)+'</strong><span class="binding-code">Código '+a.code+'</span></td><td><button type="button" class="btn small binding-key" data-bind="'+a.code+'"></button><button type="button" class="binding-clear" data-unbind="'+a.code+'" aria-label="Quitar tecla de '+esc(a.name)+'">×</button></td><td><select data-pad-bind="'+a.code+'" aria-label="Control del mando para '+esc(a.name)+'">'+padOptions.map(([id,name])=>'<option value="'+id+'">'+name+'</option>').join('')+'</select></td></tr>').join('');
  function renderBindings() {
    $$('[data-bind]').forEach(b => { b.textContent = capture===Number(b.dataset.bind)?'Pulsa una tecla…':keyText(preferences.keys[b.dataset.bind]) || 'Sin asignar'; });
    $$('[data-pad-bind]').forEach(s => { s.value = preferences.pads[s.dataset.padBind]; s.disabled = engineState.armed; });
    $$('[data-shortcut]').forEach(el => { el.textContent = keyText(preferences.keys[el.dataset.shortcut]) || 'Sin tecla'; });
    $('#driveDeadzone').value = String(preferences.deadzone);
    $('#driveDeadzoneValue').textContent = Math.round(preferences.deadzone*100)+' %';
    $('#driveStorage').textContent = storageOK ? 'Preferencias guardadas en este navegador.' : 'Las preferencias solo se conservarán mientras esta página esté abierta.';
  }
  function renderStatus() {
    if (!engineState) return;
    const p = panel(), resolved = resolvedCommands(p.commands), ready = usable() && resolved.map.has(0) && !resolved.ambiguous.length;
    $('#driveVehicleName').textContent = p.vehicle ? p.vehicle.nombre+' · ID '+p.vehicle.id_vehiculo : 'Selecciona un vehículo';
    $('#driveArm').disabled = engineState.pending || (!engineState.armed && !ready);
    $('#driveArm').textContent = engineState.armed ? 'Desactivar conducción' : 'Activar conducción';
    $('#driveArm').setAttribute('aria-pressed', String(engineState.armed));
    $('#driveMode').textContent = engineState.armed ? 'Controles activos' : engineState.pending ? 'Liberando…' : 'Controles en pausa';
    $('#driveMode').classList.toggle('live', engineState.armed);
    $('#driveStop').disabled = !p.connected || !resolved.map.has(0);
    $('#drivePower').disabled = physical() || engineState.armed || engineState.pending;
    $('#driveTransport').disabled=engineState.armed||engineState.pending||!!window.RemoteDrive?.ending();
    $('#drivePower').value = engineState.power;
    const unavailable = !p.connected ? 'Conecta la API para cargar los comandos.' : !p.vehicle ? 'Selecciona un vehículo.' : p.vehicle.activo!==1 ? 'El vehículo está inactivo.' : p.running ? 'Hay una secuencia DEMO activa.' : !p.socketOpen ? 'Se necesita el canal de eventos conectado para activar la conducción.' : physical() && !window.RemoteDrive.ready() ? (window.RemoteDrive.status()?.modo==='serial'?'El puerto serial tiene el control. Envía WIFI desde el monitor serial.':'Conecta el ESP8266 en modo WIFI; esperando confirmación de salidas liberadas.') : !resolved.map.has(0) ? 'Falta un comando activo con código 0 (parar / liberar). Agrégalo en Administración.' : resolved.ambiguous.length ? 'Hay códigos repetidos: '+resolved.ambiguous.join(', ')+'. Corrígelos en Administración.' : resolved.missing.length ? 'Faltan comandos activos: '+resolved.missing.join(', ')+'. Las acciones disponibles se pueden utilizar.' : 'Los 13 comandos y la liberación están disponibles.';
    $('#driveReadiness').textContent = window.RemoteDrive?.status()?.registro_error || unavailable;
    const deviceStatus=window.RemoteDrive?.status();
    $('#driveDeviceState').textContent=physical()?(deviceStatus?.conectado?'ESP8266 · '+deviceStatus.modo.toUpperCase()+' · salida '+deviceStatus.codigo_activo:'ESP8266 sin conexión'):'Registro de software; sin activar salidas del ESP8266.';
    $$('[data-drive]').forEach(b => {
      const code = Number(b.dataset.drive);
      b.disabled = !engineState.armed || !resolved.map.has(code) || engineState.pulse!==null || (code===9 && engineState.power==='unknown');
      b.classList.toggle('pressed', engineState.armed && engineState.active===code);
      b.setAttribute('aria-pressed', String(engineState.armed && engineState.active===code));
    });
    $$('[data-bind],[data-unbind]').forEach(b=>b.disabled=engineState.armed||engineState.pending);
    $$('[data-pad-bind]').forEach(s=>s.disabled=engineState.armed||engineState.pending);
    ['#driveDeadzone','#drivePad','#driveReset'].forEach(s=>$(s).disabled=engineState.armed||engineState.pending);
    const name = actions.find(a=>a.code===engineState.active)?.name;
    const statusText = engineState.stopFailed ? 'Liberación sin confirmar' : engineState.pending ? 'Enviando a la API…' : name && engineState.confirmed!==false ? name+(physical()?' · salidas confirmadas por el ESP8266':' · confirmado por la API') : 'Esperando una entrada';
    const statusKey = statusText + engineState.power;
    if (lastRender!==statusKey) { $('#driveActivity').textContent=statusText; lastRender=statusKey; }
    $('#drivePowerHint').textContent = engineState.power==='unknown' ? 'Antes de usar encendido, indica el estado supuesto del carro.' : 'Estado supuesto: '+(engineState.power==='on'?'encendido':'apagado')+'. Sin confirmación del dispositivo.';
    if(physical())$('#drivePowerHint').textContent=engineState.power==='unknown'?'El firmware no conoce el estado supuesto. Corrígelo por serial con ENCENDIDO 0 o ENCENDIDO 1, con las salidas liberadas.':'Estado supuesto reportado por el firmware; no hay un sensor de encendido.';
  }
  function sync() {
    const p = panel(), context = p.generation+':'+(p.vehicle?.id_vehiculo || '')+':'+physical();
    const commands = JSON.stringify(p.commands);
    const availability = [p.page,p.connected,p.running,p.socketOpen].join(':');
    if (context!==lastContext || commands!==lastCommands || availability!==lastAvailability) {
      if (engineState.armed) suspend('Cambió la conexión, el vehículo o la sección.');
      if (context!==lastContext) { controller.setPower('unknown'); controller.idle().then(()=>controller.setPower('unknown')); }
      lastContext=context; lastCommands=commands; lastAvailability=availability;
    }
    if(physical() && !engineState.armed && !engineState.pending) {
      const value=window.RemoteDrive.status()?.encendido_estimado;
      const power=value===true?'on':value===false?'off':'unknown';
      if(engineState.power!==power)controller.setPower(power);
    }
    if (engineState.armed && !usable()) suspend('La conducción quedó en pausa.');
    renderStatus();
  }
  $('#driveArm').addEventListener('click', () => {
    if (engineState.armed) { suspend('Conducción desactivada.'); return; }
    if (!usable()) return;
    const p = panel(), resolved = resolvedCommands(p.commands);
    if (!resolved.map.has(0) || resolved.ambiguous.length) return;
    clearInputs();
    if (controller.arm(targetSnapshot(p))) {
      setMessage('Mantén una tecla o botón para mover; al soltar se libera. Espacio o Esc para parar.');
      $('#driveArm').blur();
    }
  });
  function stop() {
    capture=null; clearInputs();
    const p=panel(), resolved=resolvedCommands(p.commands);
    if (!engineState.armed && !engineState.pending && resolved.map.has(0) && p.connected) {
      controller.arm(targetSnapshot(p));
    }
    const target=window.RemoteDrive?.target();
    const controlContext=controller.currentContext();
    if(controlContext)controlContext.explicitStop=true;
    controller.halt('Parada').then(()=>window.RemoteDrive?.release(target));
    setMessage('Parada solicitada. La conducción quedó en pausa.');
    renderBindings();
  }
  $('#driveStop').addEventListener('click',stop);
  function press(code,source) {
    if (!usable()) { suspend('Se perdió el foco o la conexión.'); return; }
    if (inputDown.has(source)) return;
    inputDown.add(source);
    controller.press(code,source);
  }
  function release(source) { inputDown.delete(source); controller.release(source); }
  $$('[data-drive]').forEach(b => {
    b.addEventListener('pointerdown',e=>{
      if (e.button!==0 || b.disabled) return;
      e.preventDefault(); b.setPointerCapture(e.pointerId);
      press(Number(b.dataset.drive),'pointer:'+e.pointerId);
    });
    for (const event of ['pointerup','pointercancel','lostpointercapture']) b.addEventListener(event,e=>release('pointer:'+e.pointerId));
    // Activación con tecnologías de asistencia (los punteros ya usan pointerdown).
    b.addEventListener('click',e=>{if(e.detail===0){const source='assist:'+b.dataset.drive;press(Number(b.dataset.drive),source);release(source);}});
  });
  const editing = target => target instanceof Element && !!target.closest('input,select,textarea,[contenteditable="true"],dialog');
  window.addEventListener('keydown',e=>{
    if (!onPage()) return;
    if (capture!==null) {
      e.preventDefault(); if(e.repeat)return;
      if(e.code==='Escape'){capture=null;renderBindings();return;}
      if(e.ctrlKey||e.altKey||e.metaKey||['Tab','Enter','ShiftLeft','ShiftRight','ControlLeft','ControlRight','AltLeft','AltRight'].includes(e.code)) { setMessage('Usa una tecla sin Ctrl, Alt o Windows; Esc cancela.');return; }
      if(!bindableKey(e.code)) return;
      for(const a of actions)if(preferences.keys[a.code]===e.code)preferences.keys[a.code]='';
      preferences.keys[capture]=e.code; capture=null; save();renderBindings();
      setMessage('Tecla asignada. Cada tecla controla una sola acción.');return;
    }
    if(e.code==='Escape' && engineState.armed){e.preventDefault();stop();return;}
    if(!engineState.armed||editing(e.target)||e.ctrlKey||e.altKey||e.metaKey)return;
    const action=actions.find(a=>preferences.keys[a.code]===e.code);
    if(!action)return;
    e.preventDefault(); if(e.repeat)return;
    if(action.code===0)stop();else press(action.code,'key:'+e.code);
  },true);
  window.addEventListener('keyup',e=>release('key:'+e.code));
  $('#driveBindings').addEventListener('click',e=>{
    const bind=e.target.closest('[data-bind]'), unbind=e.target.closest('[data-unbind]');
    if(bind){capture=Number(bind.dataset.bind);setMessage('Pulsa la nueva tecla. Esc cancela.');renderBindings();}
    if(unbind){preferences.keys[unbind.dataset.unbind]='';save();renderBindings();}
  });
  $('#driveBindings').addEventListener('change',e=>{
    const select=e.target.closest('[data-pad-bind]'); if(!select)return;
    const code=select.dataset.padBind,value=select.value;
    for(const a of actions)if(value&&preferences.pads[a.code]===value)preferences.pads[a.code]='';
    preferences.pads[code]=value;save();renderBindings();
  });
  $('#driveReset').addEventListener('click',()=>{preferences=defaults();capture=null;save();renderBindings();setMessage('Asignaciones originales restauradas.');});
  $('#drivePower').addEventListener('change',e=>controller.setPower(e.target.value));
  $('#driveDeadzone').addEventListener('input',e=>{preferences.deadzone=Number(e.target.value);save();renderBindings();});
  $('#drivePad').addEventListener('change',e=>{padIndex=e.target.value;lastPadId='';clearInputs();});
  function readPads() { try{return navigator.getGamepads?Array.from(navigator.getGamepads()).filter(p=>p&&p.connected):[];}catch{return [];} }
  function frame() {
    const pads=readPads(), signature=pads.map(p=>p.index+':'+p.id).join('|');
    if(signature!==padSignature){
      padSignature=signature;
      if(!pads.some(p=>String(p.index)===padIndex)) padIndex=pads[0]?String(pads[0].index):'';
      $('#drivePad').innerHTML='<option value="">Seleccionar mando</option>'+pads.map(p=>'<option value="'+p.index+'">'+esc(p.id)+'</option>').join('');
      $('#drivePad').value=padIndex;
    }
    const pad=pads.find(p=>String(p.index)===padIndex), id=pad?pad.index+':'+pad.id:'';
    if(id!==lastPadId){if(engineState.armed)suspend('El mando se conectó, cambió o desconectó.');lastPadId=id;padNeutral=false;padDown.clear();}
    const status = !window.isSecureContext ? 'El mando requiere HTTPS en EC2 o localhost en tu PC.' : !navigator.getGamepads ? 'Este navegador no admite mandos.' : !pad ? 'Conecta tu mando Xbox y pulsa un botón para detectarlo.' : pad.mapping!=='standard' ? 'Mando sin distribución estándar. Sus entradas no se usarán para conducir.' : 'Mando listo · '+pad.id;
    if($('#drivePadStatus').textContent!==status)$('#drivePadStatus').textContent=status;
    const inputs=pad&&pad.mapping==='standard'?gamepadInputs(pad,preferences.deadzone):new Set();
    if(!engineState.armed||!usable()){padNeutral=false;padDown=inputs;}
    else if(!padNeutral){if(!inputs.size){padNeutral=true;padDown.clear();}}
    else {
      // Primero las nuevas pulsaciones y después las liberaciones para evitar
      // enviar un cero intermedio al pasar directamente entre dos direcciones.
      for(const input of inputs)if(!padDown.has(input)){
        const action=actions.find(a=>preferences.pads[a.code]===input);
        if(action){if(action.code===0)stop();else press(action.code,'pad:'+input);}
      }
      for(const input of padDown)if(!inputs.has(input))release('pad:'+input);
      padDown=inputs;
    }
    requestAnimationFrame(frame);
  }
  window.addEventListener('panelchange',sync);
  window.addEventListener('blur',()=>{suspend('La ventana perdió el foco.');renderBindings();});
  window.addEventListener('focus',sync);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)suspend('La pestaña quedó oculta.');else sync();});
  window.addEventListener('gamepaddisconnected',()=>suspend('Se desconectó el mando.'));
  window.addEventListener('pagehide',()=>{
    suspend('Se cerró la página.');
    // Mejor esfuerzo en descarga: el firmware futuro debe tener su propio watchdog.
    const target=window.vehiclePanel.lastDriveTarget;
    if(target)window.vehiclePanel.releaseOnExit(target);
  });
  document.addEventListener('focusin',e=>{if(engineState.armed&&editing(e.target))suspend('Se abrió un campo de edición.');});
  new MutationObserver(()=>{if(document.querySelector('dialog[open]'))suspend('Se abrió un diálogo.');}).observe(document.body,{subtree:true,attributes:true,attributeFilter:['open']});
  window.panelDrive={suspend, sync, idle:()=>controller.idle(),isArmed:()=>controller.snapshot().armed};
  renderBindings();sync();requestAnimationFrame(frame);
})();
