export function abrirMovimientos(api, unidad, sinSesion = () => {}) {
  const dialog = document.createElement('dialog');
  dialog.className = 'movement-dialog';
  dialog.dataset.movimientos = '';
  dialog.setAttribute('aria-label', 'Movimientos de la unidad');
  dialog.innerHTML = `<div class="movement-content">
    <div class="section-title"><h2></h2><button type="button" data-close>Cerrar</button></div>
    <p>Consulta los movimientos de esta unidad, modifica sus datos o dales de baja. Puedes reactivarlos después.</p>
    <button type="button" data-refresh>Actualizar movimientos</button>
    <p role="status" aria-live="polite"></p>
    <div class="table-scroll"><table><caption>Movimientos registrados</caption>
      <thead><tr><th scope="col">Código</th><th scope="col">Movimiento</th><th scope="col">Estado</th><th scope="col">Acciones</th></tr></thead>
      <tbody></tbody></table></div>
    <section data-confirm hidden aria-label="Confirmar cambio de estado">
      <p></p><button type="button" data-accept>Confirmar</button> <button type="button" data-dismiss>Cancelar</button>
    </section>
    <form class="admin-form" hidden>
      <h3>Editar movimiento</h3>
      <label>Nombre<input name="nombre" maxlength="60" required></label>
      <label>Código del movimiento<input name="codigo" type="number" min="-2147483648" max="2147483647" step="1" required></label>
      <label>Descripción<textarea name="descripcion" maxlength="255"></textarea></label>
      <p>El código determina la acción que recibe el carro. Cámbialo solo si corresponde al movimiento deseado.</p>
      <div><button class="primary" type="submit">Guardar cambios</button> <button type="button" data-cancel>Cancelar edición</button></div>
    </form>
  </div>`;
  document.body.append(dialog);
  const form = dialog.querySelector('form'), f = form.elements;
  const rows = dialog.querySelector('tbody'), aviso = dialog.querySelector('[role=status]');
  const close = dialog.querySelector('[data-close]'), refresh = dialog.querySelector('[data-refresh]');
  const route = '/admin/vehiculos/' + unidad.id_vehiculo + '/comandos';
  const confirm = dialog.querySelector('[data-confirm]');
  let comandos = [], editing = null, pending = null, busy = false;
  dialog.querySelector('h2').textContent = 'Movimientos · ' + unidad.nombre;
  close.onclick = () => dialog.close();
  dialog.onclose = () => dialog.remove();
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });

  function element(tag, text) {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  }
  function cancel() {
    editing = null;
    form.reset();
    form.hidden = true;
  }
  function edit(command) {
    editing = command;
    f.nombre.setCustomValidity('');
    f.nombre.value = command.nombre;
    f.codigo.value = command.codigo;
    f.descripcion.value = command.descripcion || '';
    form.hidden = false;
    aviso.textContent = '';
    f.nombre.focus();
  }
  function render() {
    rows.replaceChildren(...comandos.map(command => {
      const row = document.createElement('tr');
      for (const value of [command.codigo, command.nombre, command.activo ? 'Activo' : 'Dado de baja']) {
        row.append(element('td', value));
      }
      const actions = document.createElement('td');
      const editButton = element('button', 'Editar');
      editButton.type = 'button';
      editButton.setAttribute('aria-label', 'Editar ' + command.nombre);
      editButton.onclick = () => edit(command);
      const toggle = element('button', command.activo ? 'Dar de baja' : 'Reactivar');
      toggle.type = 'button';
      toggle.setAttribute('aria-label', toggle.textContent + ' ' + command.nombre);
      toggle.onclick = () => {
        if (busy) return;
        const active = command.activo ? 0 : 1;
        cancel();
        pending = { command, active };
        confirm.querySelector('p').textContent = (active ? '¿Reactivar' : '¿Dar de baja') + ' el movimiento «' + command.nombre + '»?'
          + (active ? '' : ' Dejará de estar disponible para el control y las demos que lo usen.');
        confirm.hidden = false;
        rows.inert = refresh.disabled = true;
        confirm.querySelector('[data-accept]').focus();
      };
      actions.append(editButton, toggle);
      row.append(actions);
      return row;
    }));
  }
  async function update(command, changes) {
    const data = { nombre: command.nombre, codigo: command.codigo,
      descripcion: command.descripcion || '', activo: Number(command.activo), ...changes };
    const saved = await api.request(route + '/' + command.id_comando, { method: 'PUT', body: JSON.stringify(data) });
    if (!dialog.open) return;
    comandos = comandos.map(c => c.id_comando === saved.id_comando ? saved : c);
    render();
  }
  async function work(action) {
    if (busy || !dialog.open) return;
    busy = true;
    form.inert = rows.inert = confirm.inert = true;
    refresh.disabled = close.disabled = true;
    aviso.textContent = '';
    try { await action(); }
    catch (error) {
      if (!dialog.open) return;
      if (error.status === 401 || error.status === 403) {
        dialog.close();
        sinSesion(error);
      } else aviso.textContent = error.message;
    } finally {
      busy = false;
      form.inert = confirm.inert = close.disabled = false;
      rows.inert = refresh.disabled = Boolean(pending);
    }
  }
  async function load() {
    aviso.textContent = 'Consultando movimientos…';
    const result = await api.get(route);
    if (!dialog.open) return;
    comandos = result;
    cancel();
    render();
    aviso.textContent = comandos.length ? '' : 'Esta unidad no tiene movimientos registrados.';
  }
  function dismiss() {
    pending = null;
    confirm.hidden = true;
    rows.inert = refresh.disabled = false;
  }
  confirm.querySelector('[data-dismiss]').onclick = dismiss;
  confirm.querySelector('[data-accept]').onclick = () => {
    if (!pending || busy) return;
    const { command, active } = pending;
    dismiss();
    void work(async () => {
      await update(command, { activo: active });
      aviso.textContent = active ? 'Movimiento reactivado.' : 'Movimiento dado de baja.';
    });
  };
  form.querySelector('[data-cancel]').onclick = cancel;
  refresh.onclick = () => work(load);
  form.onsubmit = event => {
    event.preventDefault();
    if (!editing || busy) return;
    const nombre = f.nombre.value.trim();
    if (!nombre) {
      f.nombre.setCustomValidity('Escribe un nombre para el movimiento.');
      f.nombre.reportValidity();
      return;
    }
    if (!form.reportValidity()) return;
    const command = editing;
    void work(async () => {
      await update(command, { nombre, codigo: Number(f.codigo.value), descripcion: f.descripcion.value.trim() });
      cancel();
      aviso.textContent = 'Movimiento actualizado.';
    });
  };
  f.nombre.oninput = () => f.nombre.setCustomValidity('');
  dialog.showModal();
  void work(load);
}
