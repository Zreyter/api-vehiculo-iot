'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const {createHash,randomBytes} = require('node:crypto');
const {createGateway,normalizeApi} = require('../src/gateway.cjs');

async function fixture(t) {
  const received=[], sockets=new Set();
  const api=http.createServer(async(req,res)=>{
    let body='';for await(const chunk of req)body+=chunk;
    received.push({path:req.url,method:req.method,headers:req.headers,body});
    if(req.url==='/vehiculos/1/redirect'){res.writeHead(302,{Location:'http://example.com'});res.end();return;}
    res.writeHead(req.url==='/admin/denied'?401:200,{'Content-Type':'application/json'});res.end(JSON.stringify({ok:true}));
  });
  api.on('connection',socket=>{sockets.add(socket);socket.on('close',()=>sockets.delete(socket));});
  await new Promise(resolve=>api.listen(0,'127.0.0.1',resolve));
  const apiUrl='http://127.0.0.1:'+api.address().port;
  const saves=[];
  const gateway=await createGateway({apiUrl,assets:path.resolve(__dirname,'../assets'),onSave:async url=>saves.push(url)});
  t.after(async()=>{await gateway.close();for(const socket of sockets)socket.destroy();await new Promise(resolve=>api.close(resolve));});
  return {gateway,api,apiUrl,saves,received};
}
test('dirección admite HTTP/HTTPS y rechaza rutas, claves y otros protocolos',()=>{
  assert.equal(normalizeApi(' https://example.com:8443/ '),'https://example.com:8443');
  for(const value of ['file:///etc/passwd','http://user:secret@example.com','http://example.com/panel','http://example.com?token=secret','example.com'])assert.throws(()=>normalizeApi(value));
});
test('panel público empaquetado, CSP y archivos limitados',async t=>{
  const {gateway}=await fixture(t);
  const response=await fetch(gateway.origin+'/panel/');const html=await response.text();
  assert.equal(response.status,200);assert.match(html,/page-conduccion/);assert.match(html,/\/desktop\/context.js/);
  assert.match(response.headers.get('content-security-policy'),/script-src 'self'/);
  for(const file of ['.env','config_carro.h','main.cjs','../package.json'])assert.equal((await fetch(gateway.origin+'/panel/'+file)).status,404);
  assert.equal((await fetch(gateway.origin+'/panel/remote-drive.js')).status,200);
});
test('configuración guarda solamente el servidor y valida el origen',async t=>{
  const {gateway,saves}=await fixture(t);
  const response=await fetch(gateway.origin+'/desktop/connect',{method:'POST',headers:{Origin:gateway.origin,'Content-Type':'application/json'},body:JSON.stringify({apiUrl:'https://example.com:8443'})});
  assert.equal(response.status,200);assert.deepEqual(saves,['https://example.com:8443']);
  assert.equal((await (await fetch(gateway.origin+'/desktop/config')).json()).apiUrl,'https://example.com:8443');
  assert.equal((await fetch(gateway.origin+'/desktop/connect',{method:'POST',headers:{Origin:'https://evil.example','Content-Type':'application/json'},body:'{}'})).status,403);
});
test('reenvía CRUD y Authorization conservando errores de la API',async t=>{
  const {gateway,received,apiUrl}=await fixture(t);
  const response=await fetch(gateway.origin+'/vehiculos/1/control/orden',{method:'POST',headers:{Origin:gateway.origin,Authorization:'Bearer test-only','Content-Type':'application/json'},body:'{"codigo":2,"lease_id":"test-only"}'});
  assert.equal(response.status,200);assert.equal(received[0].headers.authorization,'Bearer test-only');
  assert.equal(received[0].headers.origin,apiUrl);assert.equal(received[0].body,'{"codigo":2,"lease_id":"test-only"}');
  assert.equal((await fetch(gateway.origin+'/admin/denied')).status,401);
  assert.equal((await fetch(gateway.origin+'/vehiculos/1/redirect')).status,502);
});
test('bloquea solicitudes desde otra página y rutas de dispositivo',async t=>{
  const {gateway}=await fixture(t);
  assert.equal((await fetch(gateway.origin+'/admin/vehiculos',{headers:{Origin:'https://evil.example'}})).status,403);
  assert.equal((await fetch(gateway.origin+'/admin/vehiculos',{headers:{'Sec-Fetch-Site':'cross-site'}})).status,403);
  assert.equal((await fetch(gateway.origin+'/dispositivo/ws/vehiculos/1')).status,404);
});
test('EC2 inaccesible devuelve un error utilizable en el panel',async t=>{
  const gateway=await createGateway({apiUrl:'http://127.0.0.1:1',assets:path.resolve(__dirname,'../assets')});
  t.after(()=>gateway.close());
  const response=await fetch(gateway.origin+'/admin/vehiculos');assert.equal(response.status,502);
  assert.match((await response.json()).detail,/EC2/);
});
test('WebSocket conserva token, corrige Origin y transmite eventos',{timeout:5000},async t=>{
  const {gateway,api,apiUrl}=await fixture(t);
  let headers;
  api.on('upgrade',(req,socket)=>{
    headers=req.headers;
    const accept=createHash('sha1').update(req.headers['sec-websocket-key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
    socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+'\r\nSec-WebSocket-Protocol: iot\r\n\r\n');
    const data=Buffer.from('{"tipo":"estado"}');socket.write(Buffer.concat([Buffer.from([0x81,data.length]),data]));
    socket.on('error',()=>{});
  });
  await new Promise((resolve,reject)=>{
    const request=http.request(gateway.origin+'/panel/ws/vehiculos/1',{headers:{Origin:gateway.origin,Connection:'Upgrade',Upgrade:'websocket','Sec-WebSocket-Key':randomBytes(16).toString('base64'),'Sec-WebSocket-Version':'13','Sec-WebSocket-Protocol':'iot, token.dGVzdA'} });
    request.on('error',reject);request.on('response',()=>reject(new Error('Upgrade rechazado')));
    request.on('upgrade',(response,socket,head)=>{
      const check=data=>{try{assert.match(data.toString(),/estado/);assert.equal(response.headers['sec-websocket-protocol'],'iot');socket.destroy();resolve();}catch(error){reject(error);}};
      socket.on('error',()=>{});if(head.length)check(head);else socket.once('data',check);
    });request.end();
  });
  assert.equal(headers.origin,apiUrl);assert.equal(headers['sec-websocket-protocol'],'iot, token.dGVzdA');
});
test('WebSocket rechaza origen ajeno',async t=>{
  const {gateway}=await fixture(t);
  const status=await new Promise((resolve,reject)=>{
    const request=http.request(gateway.origin+'/panel/ws/vehiculos/1',{headers:{Origin:'http://evil.example',Connection:'Upgrade',Upgrade:'websocket'}});
    request.on('error',reject);request.on('response',response=>{response.resume();resolve(response.statusCode);});request.end();
  });assert.equal(status,403);
});

test('reutiliza la conexión con EC2 y no repite una escritura fallida',async t=>{
  const {gateway,received,api}=await fixture(t);
  let connections=0;api.on('connection',()=>connections++);
  for(let i=0;i<4;i++){
    const response=await fetch(gateway.origin+'/admin/vehiculos');await response.text();
  }
  assert.equal(connections,1);assert.equal(received[0].headers.connection,'keep-alive');
  assert.equal(received.length,4);
});
