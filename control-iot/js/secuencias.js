export function abrirSecuencias(api, unidad, fabrica = false) {
  const dialog = document.createElement('dialog');
  dialog.setAttribute('aria-label', 'Editor de demos');
  dialog.innerHTML = `<form class="admin-form">
    <h2></h2><label>Secuencia<select name="lista"></select></label>
    <label>Nombre<input name="nombre" maxlength="80" required></label>
    <label>Descripción<textarea name="descripcion" maxlength="255"></textarea></label>
    <ol class="pasos"></ol><button type="button" data-add>Agregar paso</button>
    <output></output><p role="status"></p>
    <div><button type="submit" class="primary">Guardar demo</button>
    <button type="button" data-archive>Dar de baja</button><button type="button" data-close>Cerrar</button></div>
  </form>`;
  document.body.append(dialog);
  const form = dialog.querySelector('form'), f = form.elements;
  const lista = f.lista, pasos = form.querySelector('ol'), aviso = form.querySelector('[role=status]');
  const guardar = form.querySelector('[type=submit]'), archivar = form.querySelector('[data-archive]');
  const ruta = '/comercial/unidades/' + unidad.id_vehiculo + '/secuencias';
  form.querySelector('h2').textContent = (fabrica ? 'Demos de fábrica · ' : 'Mis demos · ') + unidad.nombre;
  form.querySelector('[data-close]').onclick = () => dialog.close();
  dialog.onclose = () => dialog.remove();
  let catalogo, revision = 0;
  function total() {
    const ms = [...pasos.querySelectorAll('input')].reduce((s, n) => s + Number(n.value), 0);
    form.querySelector('output').textContent = pasos.children.length + ' pasos · ' + (ms / 1000) + ' s de 120 s';
    guardar.disabled = !catalogo || !pasos.children.length || ms > 120000;
    form.querySelector('[data-add]').disabled = !catalogo?.comandos.length || pasos.children.length >= 32;
  }
  function agregar(p = {}) {
    const li = document.createElement('li');
    li.innerHTML = `<label>Movimiento<select required></select></label>
      <label>Duración (ms)<input type="number" min="1" max="60000" value="200" required></label>
      <label>Pausa (ms)<input type="number" min="0" max="60000" value="0" required></label>
      <div><button type="button">Subir</button> <button type="button">Bajar</button> <button type="button">Quitar</button></div>`;
    const select = li.querySelector('select'), [duracion, pausa] = li.querySelectorAll('input');
    for (const c of catalogo.comandos) select.add(new Option(c.nombre, c.id_comando));
    if (p.id_comando) select.value = p.id_comando;
    duracion.value = p.duracion_ms ?? 200;
    pausa.value = p.pausa_ms ?? 0;
    const [subir,bajar,quitar] = li.querySelectorAll('button');
    subir.onclick = () => { if (li.previousElementSibling) pasos.insertBefore(li,li.previousElementSibling); };
    bajar.onclick = () => { if (li.nextElementSibling) pasos.insertBefore(li.nextElementSibling,li); };
    quitar.onclick = () => { li.remove(); total(); };
    pasos.append(li);
    total();
  }
  async function elegir() {
    const actual = ++revision;
    const demo = catalogo.demos.find(d => String(d.id_demo) === lista.value);
    pasos.replaceChildren();
    f.nombre.value = demo?.nombre || '';
    f.descripcion.value = demo?.descripcion || '';
    archivar.hidden = !demo;
    total();
    if (demo) {
      const rows = await api.get(ruta + '/' + demo.id_demo);
      if (revision === actual) rows.forEach(agregar);
    } else if (catalogo.comandos.length) agregar();
  }
  async function cargar(id = '') {
    catalogo = await api.get(ruta);
    lista.replaceChildren(new Option('Nueva demo',''));
    for (const d of catalogo.demos.filter(d => Boolean(d.fabrica) === fabrica)) lista.add(new Option(d.nombre,d.id_demo));
    lista.value = id;
    await elegir();
  }
  async function trabajar(accion) {
    form.inert = true;
    aviso.textContent = '';
    try { await accion(); }
    catch (e) { aviso.textContent = e.message; }
    finally { form.inert = false; total(); }
  }
  lista.onchange = () => trabajar(elegir);
  form.querySelector('[data-add]').onclick = () => agregar();
  pasos.oninput = total;
  form.onsubmit = e => {
    e.preventDefault();
    void trabajar(async () => {
      const datos = { nombre:f.nombre.value, descripcion:f.descripcion.value,
        pasos:[...pasos.children].map(li => {
          const [duracion,pausa] = li.querySelectorAll('input');
          return { id_comando:Number(li.querySelector('select').value), duracion_ms:Number(duracion.value), pausa_ms:Number(pausa.value) };
        }) };
      const result = await api.request(ruta + (lista.value ? '/' + lista.value : ''), {
        method:lista.value ? 'PUT' : 'POST', body:JSON.stringify(datos)
      });
      await cargar(result.id_demo);
      aviso.textContent = 'Demo guardada.';
    });
  };
  archivar.onclick = () => trabajar(async () => {
    await api.request(ruta + '/' + lista.value,{method:'DELETE'});
    await cargar();
    aviso.textContent = 'Demo dada de baja.';
  });
  dialog.showModal();
  void trabajar(() => cargar());
}
