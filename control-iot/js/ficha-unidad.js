export async function abrirUnidad(api, item, recargar) {
  const dialog = document.createElement('dialog');
  dialog.setAttribute('aria-label','Ficha de unidad');
  dialog.innerHTML = `<form class="admin-form"><h2>Ficha de unidad</h2>
    <label>Nombre<input name="nombre" maxlength="80" required></label>
    <label>Modelo comercial<select name="modelo" required></select></label>
    <label>Estado comercial<select name="estado"></select></label><p role="status"></p>
    <div><button class="primary" disabled>Guardar unidad</button> <button type="button">Cerrar</button></div></form>`;
  document.body.append(dialog);
  const form = dialog.querySelector('form'), f = form.elements, aviso = form.querySelector('p');
  dialog.onclose = () => dialog.remove();
  form.querySelector('[type=button]').onclick = () => dialog.close();
  f.nombre.value = item?.nombre || '';
  const estados = item?.id_usuario ? ['asignado'] : ['disponible','exhibicion','sin_clasificar','inactivo'];
  for (const e of estados) f.estado.add(new Option(e.replace('_',' '),e));
  if (item) f.estado.value = item.estado;
  dialog.showModal();
  try {
    for (let inicio = 0;;inicio += 100) {
      const rows = await api.get('/comercial/modelos?limite=100&inicio=' + inicio);
      for (const m of rows.filter(m => m.activo)) f.modelo.add(new Option(m.nombre,m.id_modelo));
      if (rows.length < 100) break;
    }
    if (item) f.modelo.value = item.id_modelo || '';
    f.modelo.disabled = Boolean(item?.id_usuario);
    form.querySelector('.primary').disabled = !f.modelo.options.length || (f.modelo.disabled && !f.modelo.value);
    if (!f.modelo.options.length) aviso.textContent = 'Registra primero un modelo activo.';
  } catch(e) { aviso.textContent = e.message; }
  form.onsubmit = async e => {
    e.preventDefault();
    const data = {nombre:f.nombre.value,id_modelo:Number(f.modelo.value),estado:f.estado.value};
    form.inert = true;
    try {
      await api.request('/comercial/unidades' + (item ? '/' + item.id_vehiculo : ''),{
        method:item ? 'PUT' : 'POST',body:JSON.stringify(data)});
      dialog.close(); await recargar();
    } catch(err) { aviso.textContent = err.message; }
    finally { form.inert = false; }
  };
}
