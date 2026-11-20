import asyncio
import json

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from app.core.errors import ServiceError

router = APIRouter(prefix="/exhibicion",tags=["Prueba de invitados"])
DURACION = 45
PULSO_MS = 200
CODIGOS = (1,4)


@router.get("/catalogo")
async def catalogo(request: Request):
    app=request.app.state
    modelos,unidades=await asyncio.to_thread(app.comercial.exhibicion)
    for modelo in modelos:
        modelo["unidades"]=[]
    por_id={m["id_modelo"]:m for m in modelos}
    if app.settings.exhibicion_habilitada:
        for u in unidades:
            estado=app.device_service.status(u["id_vehiculo"])
            reservada = u.pop("reservada")
            u["disponible"] = bool(estado["listo"] and estado["demo_temporizada"] and not reservada
                                   and not estado["control_ocupado"])
            por_id[u.pop("id_modelo")]["unidades"].append(u)
    return {"habilitada":app.settings.exhibicion_habilitada,"modelos":modelos}


@router.websocket("/ws/{unidad}")
async def prueba(socket: WebSocket, unidad: int):
    app=socket.app.state
    origen=socket.headers.get("origin")
    local=("https" if socket.url.scheme=="wss" else "http")+"://"+socket.headers.get("host","")
    if not app.settings.exhibicion_habilitada or origen not in {local,*app.settings.browser_origins}:
        await socket.close(code=1008)
        return
    await socket.accept()
    reserva=lease=None
    motivo="desconexion"
    try:
        async with app.permisos.operacion(unidad):
            estado=app.device_service.status(unidad)
            if not estado["listo"] or not estado["demo_temporizada"]:
                raise ServiceError(409,"No hay una placa disponible para la prueba.")
            reserva,comandos=await asyncio.to_thread(app.comercial.reservar,unidad,DURACION,CODIGOS)
            vence=asyncio.get_running_loop().time()+DURACION
            lease=(await app.device_service.acquire(unidad))["lease_id"]
        await socket.send_json({"tipo":"inicio","segundos":max(0,int(vence-asyncio.get_running_loop().time())),"comandos":comandos})
        ultimo=0
        async with asyncio.timeout_at(vence):
            while True:
                raw=await asyncio.wait_for(socket.receive_text(),timeout=.85)
                if len(raw)>128:
                    raise ServiceError(422,"Mensaje demasiado largo.")
                msg=json.loads(raw)
                if msg=={"accion":"detener"}:
                    motivo="detener"
                    break
                if msg=={"accion":"latido"}:
                    await app.device_service.renew(unidad,lease)
                    continue
                if not isinstance(msg,dict) or set(msg)!={"codigo"} or type(msg["codigo"]) is not int or msg["codigo"] not in comandos:
                    raise ServiceError(403,"Comando fuera de la prueba.")
                ahora=asyncio.get_running_loop().time()
                if ahora-ultimo<1:
                    continue
                ultimo=ahora
                resultado=await app.device_service.command(unidad,lease,msg["codigo"],demo_ms=PULSO_MS,record=False)
                await socket.send_json({"tipo":"orden","enviada":bool(resultado.get("orden_enviada") or resultado.get("salidas_confirmadas"))})
    except TimeoutError:
        motivo="tiempo_agotado"
    except (WebSocketDisconnect,RuntimeError,OSError):
        pass
    except (ServiceError,ValueError) as exc:
        motivo="rechazo"
        try:
            await socket.send_json({"tipo":"error","detalle":exc.detail if isinstance(exc,ServiceError) else "Mensaje inválido."})
        except (RuntimeError,OSError):
            pass
    finally:
        try:
            if lease:
                await app.device_service.stop(unidad,lease,reason="fin_exhibicion")
        finally:
            if reserva:
                await asyncio.to_thread(app.comercial.finalizar_exhibicion,reserva,motivo)
            try:
                await socket.close(code=1000)
            except (RuntimeError,OSError):
                pass
