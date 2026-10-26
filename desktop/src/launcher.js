'use strict';
const input=document.querySelector('#apiUrl'),error=document.querySelector('#serverError'),button=document.querySelector('#openPanel');
fetch('/desktop/config').then(r=>r.json()).then(config=>{input.value=config.apiUrl;}).catch(()=>{error.hidden=false;error.textContent='No se pudo cargar la configuración.';});
document.querySelector('#serverForm').addEventListener('submit',async event=>{
  event.preventDefault();button.disabled=true;error.hidden=true;
  try {
    const response=await fetch('/desktop/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({apiUrl:input.value})});
    const result=await response.json();if(!response.ok)throw new Error(result.detail);
    location.assign('/panel/');
  }catch(e){error.textContent=e.message || 'No se pudo configurar el servidor.';error.hidden=false;button.disabled=false;}
});
