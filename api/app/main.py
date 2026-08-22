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

La API key de Anthropic vive SOLO en la variable de entorno
ANTHROPIC_API_KEY del servicio desplegado -- nunca en el front ni en el repo.
"""
from __future__ import annotations

import json
import os
from contextlib import AsyncExitStack, asynccontextmanager

import anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

SYSTEM_PROMPT = (
    "Respondes preguntas sobre datos publicos de contratacion de obra publica "
    "en Colombia (SECOP II) usando las tools de Plomada disponibles. "
    "'Riesgo' aqui es un indicio para priorizar investigacion periodistica y "
    "control social, NUNCA prueba de un delito: no afirmes que un contrato "
    "marcado es fraude, di que presenta indicios y cuales. Si una tool no "
    "encuentra nada, dilo -- no inventes cifras ni nombres."
)

mcp_app = mcp.streamable_http_app(streamable_http_path="/")


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

client = anthropic.Anthropic()  # ANTHROPIC_API_KEY desde el entorno


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
def chat(req: ChatRequest):
    messages = [{"role": t.role, "content": t.content} for t in req.historial]
    messages.append({"role": "user", "content": req.mensaje})

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
