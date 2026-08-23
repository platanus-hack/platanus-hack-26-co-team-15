"""Proxy de chat para el tablero de Plomada.

Recibe preguntas del front en `POST /chat` y las responde con Claude,
usando el MCP connector remoto para que Claude consulte los datos reales de
Plomada a traves de las tools en `app.mcp.server`. Plan completo: MCP.md en
la raiz del repo.

Un solo proceso sirve dos cosas en el mismo puerto (necesario en Render, que
solo expone un puerto por servicio):
  - `/mcp`   el servidor MCP (streamable-http), llamado por la API de Claude.
  - `/chat`  el proxy que el front consume, que le pasa a Claude la URL
             publica de este mismo servicio para que use `/mcp`.

BYOK (bring your own key): cada usuario provee SU PROPIA API key de
Anthropic (la saca de console.anthropic.com) en el header `X-Anthropic-Api-Key`
de cada request. Este servicio nunca la guarda -- se usa en memoria para esa
sola llamada y se descarta. No existe una API key "del equipo" en Render: el
uso lo paga cada usuario, no Plomada. El front la guarda en localStorage del
navegador; ver MCP.md para el contrato exacto.
"""
from __future__ import annotations

import json
import os
from contextlib import AsyncExitStack, asynccontextmanager
from urllib.parse import urlparse

import anthropic
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel

from app.mcp.server import mcp

MODEL = "claude-opus-5"
MCP_BETA = "mcp-client-2025-11-20"
MCP_SERVER_NAME = "plomada"

# URL publica de ESTE MISMO servicio + la ruta del MCP montado abajo.
# Claude llama a esta URL desde la nube de Anthropic: en local, sin tunel
# (ngrok/Cloudflare Tunnel), Claude no puede alcanzarla -- ver MCP.md.
SELF_URL = os.environ.get("SELF_URL", "http://127.0.0.1:8000")
MCP_SERVER_URL = SELF_URL.rstrip("/") + "/mcp"
SELF_HOST = urlparse(SELF_URL).netloc

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

SYSTEM_PROMPT = (
    "Respondes preguntas sobre datos publicos de contratacion de obra publica "
    "en Colombia (SECOP II) usando las tools de Plomada disponibles. "
    "'Riesgo' aqui es un indicio para priorizar investigacion periodistica y "
    "control social, NUNCA prueba de un delito: no afirmes que un contrato "
    "marcado es fraude, di que presenta indicios y cuales. Si una tool no "
    "encuentra nada, dilo -- no inventes cifras ni nombres."
)

# Proteccion anti DNS-rebinding del transporte MCP: por defecto rechaza
# cualquier Host que no este en la lista blanca (vacia por defecto), con
# 421 "Invalid Host header" -- probado contra el deploy real en Render antes
# de agregar esto. SELF_HOST cubre tanto el host publico (Render) como
# localhost:8000 en desarrollo, segun de donde salga SELF_URL.
mcp_app = mcp.streamable_http_app(
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(allowed_hosts=[SELF_HOST]),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        # sin esto el servidor MCP monta las rutas pero nunca arranca su
        # session manager -- Starlette no propaga el lifespan de un sub-app
        # montado automaticamente, hay que entrarlo a mano. Verificado con
        # una prueba de humo antes de dejarlo asi.
        await stack.enter_async_context(mcp_app.router.lifespan_context(mcp_app))
        yield


app = FastAPI(title="Plomada API", lifespan=lifespan)
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )


class Turno(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    mensaje: str
    historial: list[Turno] = []


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/chat")
def chat(req: ChatRequest, x_anthropic_api_key: str = Header(alias="X-Anthropic-Api-Key")):
    messages = [{"role": t.role, "content": t.content} for t in req.historial]
    messages.append({"role": "user", "content": req.mensaje})
    # Cliente nuevo por request, con la key que mando el usuario -- nunca un
    # cliente compartido con una key del servidor (no existe tal cosa aqui).
    client = anthropic.Anthropic(api_key=x_anthropic_api_key)

    def generar():
        # El front debe poder mostrar "el asistente no esta disponible" en
        # vez de que se le caiga la conexion -- mismo criterio que el
        # tablero con alertas.json opcional (ver MCP.md).
        try:
            with client.beta.messages.stream(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                betas=[MCP_BETA],
                mcp_servers=[{"type": "url", "url": MCP_SERVER_URL, "name": MCP_SERVER_NAME}],
                tools=[{"type": "mcp_toolset", "mcp_server_name": MCP_SERVER_NAME}],
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield "data: %s\n\n" % json.dumps({"delta": text}, ensure_ascii=False)
        except anthropic.AuthenticationError:
            yield "data: %s\n\n" % json.dumps({"error": "Tu API key de Anthropic no es valida"})
            return
        except anthropic.RateLimitError:
            yield "data: %s\n\n" % json.dumps({"error": "Limite de uso alcanzado, intenta mas tarde"})
            return
        except anthropic.APIStatusError as e:
            yield "data: %s\n\n" % json.dumps({"error": "Error de la API (%s)" % e.status_code})
            return
        except anthropic.APIConnectionError:
            yield "data: %s\n\n" % json.dumps({"error": "No se pudo conectar con el asistente"})
            return
        except Exception:
            yield "data: %s\n\n" % json.dumps({"error": "El asistente no esta disponible ahora"})
            return
        yield "data: %s\n\n" % json.dumps({"done": True})

    return StreamingResponse(generar(), media_type="text/event-stream")


app.mount("/mcp", mcp_app)
