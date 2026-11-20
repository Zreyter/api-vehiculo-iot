"""Coordina permisos con las operaciones en vuelo del proceso único de control."""
import asyncio
from contextlib import asynccontextmanager

from app.core.claves_comerciales import huella


class PermisosOperativos:
    def __init__(self):
        self.cambios = asyncio.Lock()
        self.condicion = asyncio.Condition()
        self.lectores = {}
        self.en_cambio = False
        self.unidad_en_cambio = None
        self.canales = {}

    @asynccontextmanager
    async def operacion(self, unidad):
        async with self.condicion:
            await self.condicion.wait_for(lambda: not self.en_cambio or
                                          self.unidad_en_cambio not in (None, unidad))
            self.lectores[unidad] = self.lectores.get(unidad, 0) + 1
        try:
            yield
        finally:
            async with self.condicion:
                self.lectores[unidad] -= 1
                if not self.lectores[unidad]:
                    del self.lectores[unidad]
                    self.condicion.notify_all()

    @asynccontextmanager
    async def cambio(self, unidad=None):
        async with self.cambios:
            try:
                async with self.condicion:
                    self.en_cambio, self.unidad_en_cambio = True, unidad
                    await self.condicion.wait_for(lambda: not self.lectores if unidad is None
                                                  else unidad not in self.lectores)
                yield
            finally:
                async with self.condicion:
                    self.en_cambio = False
                    self.condicion.notify_all()

    def registrar(self, tarea, unidad, usuario, token):
        self.canales[tarea] = (unidad, usuario, huella(token))
        tarea.add_done_callback(lambda t: self.canales.pop(t, None))

    async def cerrar(self, *, unidad=None, usuario=None, token=None):
        clave = huella(token) if token else None
        tareas = [t for t, (v, u, k) in self.canales.items()
                  if v == unidad or (usuario is not None and u == usuario) or k == clave]
        for tarea in tareas:
            tarea.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)
