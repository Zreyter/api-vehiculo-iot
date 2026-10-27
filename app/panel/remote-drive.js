'use strict';
(() => {
  const bridge = window.vehiclePanel, legacySend = bridge.sendDrive.bind(bridge), legacyExit = bridge.releaseOnExit.bind(bridge);
  let device = null, activeTarget = null, ending = false, polling = false, context = '', lastPage = '';
  const physical = () => $('#driveTransport').value === 'wifi';
  const call = (method, suffix, target, body, options={}) => api(method, '/vehiculos/'+target.vehicle+suffix, body,
    {token:target.token,generation:target.generation,quiet:true,...options});
  function publish() { window.dispatchEvent(new Event('panelchange')); }
  async function release(target) {
    if(!target || target.transport!=='wifi' || target.finished) return;
    target.finished=true;ending=true;clearInterval(target.renewTimer);publish();
    try {
      if(target.acquiring)await target.acquiring.catch(()=>{});
      if(target.lease)await call('DELETE','/control',target,{lease_id:target.lease},{keepalive:true});
    } catch { /* El servidor y la placa conservan sus temporizadores de expiración. */ }
    finally {if(activeTarget===target)activeTarget=null;ending=false;device=null;publish();refresh();}
  }
  function startRenewal(target) {
    target.lastRenewal=performance.now();
    target.renewing=0;
    target.renewTimer=setInterval(async()=>{
      if(target.finished || activeTarget!==target)return;
      if(document.hidden || !document.hasFocus() || !window.panelDrive?.isArmed() || performance.now()-target.lastRenewal>650) {
        window.panelDrive?.suspend('Se interrumpió la renovación del control WiFi.');return;
      }
      if(target.renewing>=2)return;
      target.renewing++;
      const started=performance.now();
      try {
        await call('PUT','/control',target,{lease_id:target.lease},{timeoutMs:600});
        if(target.finished || activeTarget!==target)return;
        if(performance.now()-started>650){window.panelDrive?.suspend('La confirmación de renovación llegó demasiado tarde.');return;}
        target.lastRenewal=performance.now();
      }
      catch(error) {
        if(!target.finished && activeTarget===target)window.panelDrive?.suspend(error.message+' La conducción quedó en pausa.');
      }
      finally {target.renewing--;}
    },200);
  }
  async function acquire(target) {
    if(target.acquiring)return target.acquiring;
    activeTarget=target;
    target.acquiring=(async()=>{
      const result=await call('POST','/control',target);
      target.lease=result.lease_id;
      if(!target.finished)startRenewal(target);
      return result;
    })().catch(error=>{target.acquireFailed=true;if(activeTarget===target)activeTarget=null;throw error;});
    return target.acquiring;
  }
  bridge.prepareDrive=async function(target) {
    if(target.transport==='wifi')await acquire(target);
  };
  bridge.sendDrive=async function(code,target,options={}) {
    if(target.transport!=='wifi')return legacySend(code,target);
    if(code===0 && target.acquireFailed)return {cancelado:true};
    this.lastDriveTarget=target;
    if(code===0 && !target.acquiring) {
      // Una suspensión automática sin lease nunca debe parar al operador serial
      // ni a otro navegador. La parada global exige el botón/tecla explícitos.
      if(!target.explicitStop){this.lastDriveTarget=null;return {cancelado:true};}
      // El botón Parar también funciona sin sesión previa ni comando 0 en RDS.
      const result=await call('DELETE','/control',target,undefined,{keepalive:true});
      if(!result.salidas_confirmadas)throw new Error('La placa no confirmó la liberación de salidas.');
      this.lastDriveTarget=null;return result;
    }
    await acquire(target);
    if(code!==0 && (target.finished || options.stillWanted?.()===false))return {cancelado:true};
    const result=await call('POST','/control/orden',target,{lease_id:target.lease,codigo:code},{keepalive:code===0});
    if(code===0)this.lastDriveTarget=null;
    return result;
  };
  bridge.releaseOnExit=function(target) {
    if(target.transport!=='wifi')return legacyExit(target);
    clearInterval(target.renewTimer);
    if(target.lease)fetch('/vehiculos/'+target.vehicle+'/control',{method:'DELETE',keepalive:true,
      headers:{Authorization:'Bearer '+target.token,'Content-Type':'application/json'},
      body:JSON.stringify({lease_id:target.lease})}).catch(()=>{});
  };
  async function refresh() {
    const p=bridge.snapshot(), key=p.generation+':'+(p.vehicle?.id_vehiculo||'');
    if(key!==context){context=key;device=null;publish();}
    if(polling||!p.connected||!p.vehicle||p.page!=='conduccion'||document.hidden)return;
    polling=true;
    try {
      const result=await api('GET','/vehiculos/'+p.vehicle.id_vehiculo+'/dispositivo',undefined,{quiet:true});
      if(context===key)device=result;
    }catch{if(context===key)device=null;}
    finally{polling=false;publish();}
  }
  $('#driveTransport').addEventListener('change',()=>{window.panelDrive?.suspend('Cambió el tipo de control.');device=null;publish();refresh();});
  window.addEventListener('panelchange',()=>{
    const p=bridge.snapshot(), key=p.generation+':'+(p.vehicle?.id_vehiculo||'');
    if(key!==context){context=key;device=null;queueMicrotask(refresh);}
    if(p.page!==lastPage){lastPage=p.page;if(p.page==='conduccion')queueMicrotask(refresh);}
  });
  setInterval(refresh,1000);
  window.RemoteDrive={physical,release,refresh,target:()=>activeTarget,ending:()=>ending,
    status:()=>device,ready:()=>!ending&&!!device?.listo&&device?.modo==='wifi'};
})();
