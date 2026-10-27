'use strict';
const http = require('node:http');
const https = require('node:https');
const fs = require('node:fs');
const path = require('node:path');

const DEFAULT_API = 'http://3.233.212.203:8000';
const PANEL_FILES = new Set(['panel.css','panel.js','drive-controller.js','driving.js','remote-drive.js']);
const CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'";

function normalizeApi(value) {
  let url;
  try {url = new URL(String(value).trim());} catch {throw new Error('Escribe una dirección completa, por ejemplo http://3.233.212.203:8000');}
  if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || !['','/'].includes(url.pathname)) {
    throw new Error('Usa http:// o https://, el servidor y su puerto, sin rutas ni credenciales.');
  }
  return url.origin;
}

async function createGateway({apiUrl = DEFAULT_API, assets, onSave = async () => {}}) {
  let target = normalizeApi(apiUrl);
  let origin, revision=0, closing=false;
  const upstreams = new Set(), connections = new Set();
  // El historial nunca consume los sockets reservados al control o sus latidos.
  const agents=Object.fromEntries(['general','control','renewal'].map(group=>{
    const options={keepAlive:true,maxSockets:group==='general'?8:group==='control'?4:2,
      maxFreeSockets:2,timeout:1000,scheduling:'lifo'};
    return [group,{http:new http.Agent(options),https:new https.Agent(options)}];
  }));
  const destroyAgents=()=>{for(const group of Object.values(agents)){group.http.destroy();group.https.destroy();}};
  const send = (res, status, value, type='application/json; charset=utf-8') => {
    res.writeHead(status, {'Content-Type':type,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
      'Referrer-Policy':'no-referrer','Content-Security-Policy':CSP});
    res.end(type.startsWith('application/json') ? JSON.stringify(value) : value);
  };
  function permitted(req) {
    return req.headers.host === new URL(origin).host && (!req.headers.origin || req.headers.origin === origin)
      && !['cross-site','same-site'].includes(req.headers['sec-fetch-site']);
  }
  function proxyOptions(req,group='general') {
    const base = new URL(target);
    return {protocol:base.protocol, hostname:base.hostname.replace(/^\[|\]$/g,''), port:base.port || undefined,
      method:req.method, path:req.url, headers:{...req.headers, host:base.host, origin:base.origin,
        'accept-encoding':'identity', connection:'keep-alive'},
      agent:base.protocol==='https:' ? agents[group].https : agents[group].http};
  }
  function transport() {return target.startsWith('https:') ? https : http;}
  const server = http.createServer(async (req,res) => {
    try {
      if (!permitted(req)) return send(res,403,{detail:'Origen local no permitido.'});
      const url = new URL(req.url,origin);
      if (url.pathname === '/desktop/config' && req.method === 'GET') return send(res,200,{apiUrl:target,version:'1.6.4'});
      if (url.pathname === '/desktop/connect' && req.method === 'POST') {
        if (req.headers.origin !== origin || !req.headers['content-type']?.startsWith('application/json')) return send(res,403,{detail:'Solicitud no permitida.'});
        let body='';
        for await (const chunk of req) {body += chunk; if(body.length>4096)return send(res,413,{detail:'Configuración demasiado grande.'});}
        let next;
        try {next=normalizeApi(JSON.parse(body).apiUrl);} catch(error) {return send(res,400,{detail:error.message});}
        await onSave(next);
        revision++;
        for(const remote of upstreams) remote.destroy();
        destroyAgents();
        target=next;
        return send(res,200,{apiUrl:target});
      }
      if (['GET','HEAD'].includes(req.method)) {
        let file;
        if (url.pathname === '/' || url.pathname === '/desktop/') file=path.join(__dirname,'launcher.html');
        else if (['/desktop/launcher.js','/desktop/launcher.css','/desktop/context.js','/desktop/desktop.css'].includes(url.pathname)) file=path.join(__dirname,path.basename(url.pathname));
        else if (url.pathname === '/desktop/icon.png') file=path.join(assets,'icon.png');
        else if (url.pathname === '/panel' || url.pathname === '/panel/') {
          let html=fs.readFileSync(path.join(assets,'panel/index.html'),'utf8');
          html=html.replace('</head>','<link rel="stylesheet" href="/desktop/desktop.css"></head>')
            .replace('</body>','<script src="/desktop/context.js" defer></script></body>');
          return send(res,200,req.method==='HEAD'?'':html,'text/html; charset=utf-8');
        } else if(url.pathname.startsWith('/panel/') && PANEL_FILES.has(url.pathname.slice(7))) file=path.join(assets,'panel',url.pathname.slice(7));
        if(file) {
          const ext=path.extname(file);
          const type={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.png':'image/png'}[ext];
          return send(res,200,req.method==='HEAD'?'':fs.readFileSync(file),type);
        }
      }
      if(!/^\/(admin|vehiculos)(\/|\?|$)/.test(req.url) || !['GET','POST','PUT','DELETE','PATCH'].includes(req.method)) return send(res,404,{detail:'Ruta no disponible.'});
      const control=/^\/vehiculos\/[1-9]\d*\/control(?:\/orden)?$/.test(url.pathname);
      const renewal=control && req.method==='PUT' && url.pathname.endsWith('/control');
      const replayable=req.method==='GET' || renewal;
      const generation=revision, clientTransport=transport(), options=proxyOptions(req,renewal?'renewal':control?'control':'general');
      let body, remote, retries=0, responded=false;
      if(replayable){
        const chunks=[];let length=0;
        for await(const chunk of req){
          length+=chunk.length;if(length>4096)return send(res,413,{detail:'Petición de consulta o renovación demasiado grande.'});
          chunks.push(chunk);
        }
        body=Buffer.concat(chunks);
      }
      function forward(fresh=false){
        if(closing || req.aborted || res.destroyed || generation!==revision)return;
        const attempt=clientTransport.request(fresh?{...options,agent:false,headers:{...options.headers,connection:'close'}}:options,response=>{
          responded=true;
          if(res.destroyed || generation!==revision){response.destroy();return;}
          if(response.statusCode>=300 && response.statusCode<400){response.resume();return send(res,502,{detail:'La API devolvió una redirección. Revisa la dirección del servidor.'});}
          res.writeHead(response.statusCode,{'Content-Type':response.headers['content-type'] || 'application/json',
            'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':CSP});
          response.on('error',()=>res.destroy());response.pipe(res);
        });
        remote=attempt;upstreams.add(attempt);attempt.on('close',()=>upstreams.delete(attempt));
        attempt.setTimeout(25000,()=>attempt.destroy(Object.assign(new Error('Tiempo agotado.'),{code:'UPSTREAM_TIMEOUT'})));
        attempt.on('error',error=>{
          if(replayable && !retries && attempt.reusedSocket && error.code==='ECONNRESET' && !responded &&
             !closing && !req.aborted && !res.destroyed && generation===revision){
            retries++;forward(true);return;
          }
          if(res.destroyed || res.writableEnded)return;
          const known=new Set(['ECONNRESET','ECONNREFUSED','ENOTFOUND','EAI_AGAIN','ETIMEDOUT','EPIPE','UPSTREAM_TIMEOUT']);
          if(!res.headersSent)send(res,502,{detail:'No se pudo contactar con EC2. Comprueba el servidor, el puerto y tu conexión.',
            codigo_red:known.has(error.code)?error.code:'UPSTREAM_ERROR'});
          else res.destroy();
        });
        if(replayable)attempt.end(body);else req.pipe(attempt);
      }
      req.on('aborted',()=>remote?.destroy());
      res.on('close',()=>{if(!res.writableFinished)remote?.destroy();});
      forward();
    } catch {
      if(!res.headersSent)send(res,500,{detail:'No se pudo completar la petición local.'});else res.destroy();
    }
  });
  server.on('connection',socket=>{socket.setNoDelay(true);connections.add(socket);socket.on('close',()=>connections.delete(socket));});
  server.on('upgrade',(req,socket,head)=>{
    if(!permitted(req) || req.headers.origin!==origin || !/^\/panel\/ws\/vehiculos\/[1-9]\d*$/.test(req.url)) {
      socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');return;
    }
    const options=proxyOptions(req);options.headers.connection='Upgrade';
    const remote=transport().request(options);
    upstreams.add(remote);remote.on('close',()=>upstreams.delete(remote));
    const fail=()=>{if(!socket.destroyed)socket.destroy();};
    remote.on('error',fail);remote.setTimeout(10000,()=>remote.destroy());
    socket.on('error',()=>remote.destroy());
    socket.on('close',()=>remote.destroy());
    remote.on('upgrade',(response,peer,remoteHead)=>{
      remote.setTimeout(0);peer.setTimeout(0);peer.setNoDelay(true);upstreams.add(peer);
      let headers='HTTP/1.1 101 Switching Protocols\r\n';
      for(let i=0;i<response.rawHeaders.length;i+=2)headers+=response.rawHeaders[i]+': '+response.rawHeaders[i+1]+'\r\n';
      socket.write(headers+'\r\n');
      if(remoteHead.length)socket.write(remoteHead);
      if(head.length)peer.write(head);
      socket.pipe(peer);peer.pipe(socket);
      peer.on('error',fail);peer.on('close',()=>{upstreams.delete(peer);fail();});
      socket.on('close',()=>peer.destroy());
    });
    remote.on('response',response=>{
      socket.write('HTTP/1.1 '+response.statusCode+' Rejected\r\nConnection: close\r\n\r\n');
      response.pipe(socket);
    });
    remote.end();
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  origin='http://127.0.0.1:'+server.address().port;
  return {origin, apiUrl:()=>target, async close(){
    closing=true;
    for(const remote of upstreams)remote.destroy();
    destroyAgents();
    for(const socket of connections)socket.destroy();
    await new Promise(resolve=>server.close(resolve));
  }};
}
module.exports={createGateway,normalizeApi,DEFAULT_API};
