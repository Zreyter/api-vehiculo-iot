/* A physical sequence only continues while its starting page renews it. */
(function(root) {
  'use strict';
  class DemoControl {
    constructor({renew, connected, lost, every=(fn,ms)=>setInterval(fn,ms), clear=id=>clearInterval(id)}) {
      Object.assign(this, {renew, connected, lost, every, clear});
      this.run=null; this.timer=null; this.finished=new Set();
    }
    stop() {
      if(this.timer!==null) this.clear(this.timer);
      this.timer=null; this.run=null;
    }
    event(event) {
      if(!['demo_finalizada','demo_cancelada','error'].includes(event.tipo) || !event.id_ejecucion) return;
      this.finished.add(event.id_ejecucion);
      if(this.finished.size>32) this.finished.delete(this.finished.values().next().value);
      if(this.run?.id===event.id_ejecucion) this.stop();
    }
    start(event, vehicle) {
      this.stop();
      if(event.modo_demo!=='fisico' || !event.id_ejecucion || this.finished.has(event.id_ejecucion)) return false;
      const run={id:event.id_ejecucion,vehicle,busy:false};
      this.run=run;
      const tick=async()=>{
        if(this.run!==run || run.busy) return;
        if(!this.connected(vehicle)) {this.stop();this.lost();return;}
        run.busy=true;
        try {await this.renew(vehicle,run.id);}
        catch {if(this.run===run){this.stop();this.lost();}}
        finally {run.busy=false;}
      };
      this.timer=this.every(tick,250);
      tick();
      return this.run===run;
    }
  }
  if(typeof module==='object' && module.exports) module.exports={DemoControl};
  else root.DemoControl=DemoControl;
})(typeof globalThis!=='undefined'?globalThis:this);
