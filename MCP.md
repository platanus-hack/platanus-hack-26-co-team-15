# Plomada conversacional: MCP + Claude en el tablero

Plan de implementación para que cualquier IA (Claude, y a futuro Gemini) pueda
responder preguntas sobre los datos de Plomada **conversando desde el
tablero**, en vez de solo mirando gráficos y tablas. Este documento es para
el equipo y para quien trabaje el front — no requiere leer el resto del
código para entender qué construir y en qué orden.

**Estado: servidor MCP y proxy de chat construidos y probados localmente
(`api/app/mcp/server.py`, `api/app/main.py`). Falta el último tramo — probar
contra una URL pública real (túnel o deploy) — antes de conectar el front.**
Ver "Qué se probó" más abajo para el detalle exacto.

## Por qué esta arquitectura

La API de Claude (Messages API) tiene un **MCP connector** nativo: le pasas
la URL de un servidor MCP en la propia llamada y Claude decide cuándo llamar
sus tools — no hay que escribir el loop de tool-calling a mano. Eso hace que
la pieza que hay que construir sea, en esencia, un servidor MCP con tools de
solo lectura sobre los datos que ya existen, más un proxy delgado que
guarde la API key.

Tres decisiones de diseño para no sobreconstruir:

1. **Un solo servicio, no tres.** El esqueleto `api/` (FastAPI + Dockerfile)
   ya existe y está vacío — el proxy de chat y el servidor MCP viven ahí
   mismo, como dos rutas de la misma app. No hace falta un servicio nuevo en
   Render por cada pieza.
2. **Lee de lo que ya existe, no espera a Postgres.** Las tools consultan
   `data/exports/base.parquet` y los JSON que `pipeline/export_web.py` ya
   genera en `web/data/`. `pipeline/load_postgres.py` (item 5 de "Pendiente"
   en el README) sigue sin construirse, y no es un bloqueo: el día que exista,
   se cambia de dónde leen las tools sin tocar su contrato ni el front.
3. **Solo lectura por construcción.** La conexión DuckDB que usan las tools
   es read-only. No hay superficie de escritura que asegurar.

## Arquitectura

```
┌─────────────┐        POST /chat         ┌───────────────────────────────┐
│  web/ (front)│ ────────────────────────▶ │  api/ (Render)                │
│  chat widget │ ◀──────────────────────── │  ┌─────────────────────────┐  │
└─────────────┘   streaming (SSE)          │  │ proxy de chat            │  │
                                            │  │ POST /chat               │  │
                                            │  │ - guarda ANTHROPIC_API_KEY│ │
                                            │  │ - llama a Claude con     │  │
                                            │  │   mcp_servers + toolset  │  │
                                            │  └───────────┬─────────────┘  │
                                            │              │ Claude llama   │
                                            │              │ tools MCP      │
                                            │  ┌───────────▼─────────────┐  │
                                            │  │ servidor MCP  (/mcp)     │  │
                                            │  │ tools de solo lectura    │  │
                                            │  └───────────┬─────────────┘  │
                                            └──────────────┼────────────────┘
                                                            │
                                                data/exports/base.parquet
                                                web/data/*.json
```

El front **nunca** habla directo con Claude ni con el servidor MCP — solo con
`POST /chat` en `api/`. Eso es lo único que el agente del front necesita
integrar.

## Piezas a construir

### 1. Servidor MCP — `api/app/mcp/server.py` (construido)

SDK oficial de Python (`mcp`, versión 2.x — **exige Python ≥3.10**; el
pipeline sigue fijado a 3.9, por eso `api/` tiene su propio entorno y sus
propias dependencias en `api/requirements.txt`, igual que ya hacía con
FastAPI/Postgres).

Tools implementadas hoy (cada una una consulta DuckDB acotada a `LIMIT_DURO
= 50` filas, para no volcar tablas completas al contexto del modelo):

| Tool | Qué responde | Fuente |
|---|---|---|
| `resumen_indicios` | Cifras titulares (contratos atípicos, plata en riesgo) | `web/data/titulares.json`, `meta.json` |
| `buscar_contratos_atipicos(entidad?, departamento?, tipo_contrato?, valor_minimo?, limite=20)` | Lista de contratos marcados, con sus banderas | `data/exports/puntajes.parquet` |
| `perfil_entidad(nombre_o_nit)` | Resumen de una entidad: contratos, valor, atípicos | `data/exports/puntajes.parquet` |

Pendientes de agregar (mismo patrón, solo falta escribir la tool): `buscar_proveedor`
(red, `web/data/red.json`) y `alertas_preadjudicacion` (`web/data/alertas.json`).
Repártanlas entre los dueños de cada pilar — quien escribió `06_banderas_grafo.sql`
sabe mejor qué exponer en `buscar_proveedor`, quien escribió `alertas.py` sabe
qué exponer en `alertas_preadjudicacion`.

Correr en local:
```
python -m venv .venv-mcp
.venv-mcp/Scripts/pip install -r api/requirements.txt
.venv-mcp/Scripts/python api/app/mcp/test_smoke.py           # via stdio, sin nada mas corriendo
.venv-mcp/Scripts/python api/app/mcp/server.py --http &      # via http, puerto 8765
.venv-mcp/Scripts/python api/app/mcp/test_smoke.py --http
```

### 2. Proxy de chat — `api/app/main.py` (construido)

- `POST /chat`, recibe `{mensaje, historial?}`, responde streaming (SSE).
- Llama a la Messages API de Claude con:
  ```python
  client.beta.messages.stream(
      model="claude-opus-5", max_tokens=4096,
      betas=["mcp-client-2025-11-20"],
      mcp_servers=[{"type": "url", "url": MCP_SERVER_URL, "name": "plomada"}],
      tools=[{"type": "mcp_toolset", "mcp_server_name": "plomada"}],
      messages=messages,
  )
  ```
  Las dos partes (`mcp_servers` + `tools` con `mcp_toolset`) son obligatorias
  — mandar una sin la otra lo rechaza la API.
- `ANTHROPIC_API_KEY` vive como variable de entorno en Render — **nunca** en
  el front ni en el repo.
- Errores (auth, rate limit, MCP inalcanzable) se devuelven como un evento
  SSE `{"error": "..."}` en vez de tumbar la conexión — el front debe leer
  ese caso y mostrar "el asistente no está disponible ahora".

**Detalle técnico importante para quien lo toque:** `/mcp` y `/chat` viven en
el **mismo proceso FastAPI** (necesario en Render, que solo expone un puerto
por servicio) montando el sub-app del servidor MCP (`mcp.streamable_http_app()`)
dentro de la app de FastAPI. Eso por sí solo **no alcanza**: Starlette no
propaga el lifespan de un sub-app montado automáticamente, así que el
"session manager" del MCP nunca arranca y toda request a `/mcp` revienta con
`RuntimeError: Task group is not initialized`. Se resuelve combinando los
lifespans a mano con `AsyncExitStack` (ver `api/app/main.py`, función
`lifespan`) — verificado con una prueba real antes de dejarlo así, no es
una suposición.

Esto de paso le da un uso real al esqueleto `api/` que llevaba vacío desde
antes (ver ítem 5 de "Pendiente" en el README).

### 3. Widget de chat en el front — para quien trabaje `web/` (o el proyecto Vercel nuevo)

Todo lo que necesita saber, sin tocar nada de lo de arriba:

- **Endpoint:** `POST {API_URL}/chat`
- **Body:** `{ "mensaje": "...", "historial": [...] }` (el equipo de backend
  define el shape exacto al implementar el proxy; esto es el contrato
  mínimo).
- **Respuesta:** streaming de texto (SSE) — el widget debe leer un stream,
  no esperar un JSON completo.
- `API_URL` sale de una variable de entorno/config, para que el mismo front
  sirva en local y en producción sin cambiar código.
- Si el backend no responde, degradar con un mensaje tipo "el asistente no
  está disponible ahora" — mismo patrón que ya usa el tablero con
  `alertas.json` cuando nadie corrió `pipeline/alertas.py` (ver
  `web/index.html`, función `drawAlertas`).

## Orden de trabajo — qué ya está hecho

1. ✅ Servidor MCP corriendo local, probado con un cliente MCP real
   (`api/app/mcp/test_smoke.py`) por **stdio y por HTTP**, contra datos
   reales del warehouse.
2. ✅ `/chat` construido en `api/app/main.py`, con `/mcp` montado en el mismo
   proceso (verificado: arranca, `/health` responde, `/mcp` responde).
3. ✅ **Confirmado el límite que ya preveíamos:** al probar `/chat` de
   verdad (con una API key real, pidiéndole a Claude una pregunta), la
   respuesta de Anthropic fue exactamente:
   > `"Connection error while communicating with MCP server. The server may
   > be unavailable or unresponsive."`

   porque `MCP_SERVER_URL` apuntaba a `http://127.0.0.1:8000/mcp` — Claude
   corre en la nube de Anthropic y no puede alcanzar `localhost`. Esto no es
   un bug: es exactamente la limitación que ya estaba documentada antes de
   escribir código. **Sin excepción, no hay forma de probar el flujo
   completo sin una URL pública** (ni siquiera ejecutando todo en la misma
   máquina).

## Lo que falta — bloqueado en infraestructura, no en código

4. **Conseguir una URL pública** para `api/` — un túnel (ngrok, Cloudflare
   Tunnel) para probar rápido, o ya el deploy real a Render. Ninguna
   herramienta de túnel estaba disponible en este entorno de prueba (no hay
   `ngrok`/`cloudflared`/`npx` instalados), así que alguien del equipo con
   acceso a instalar herramientas o a la cuenta de Render tiene que dar este
   paso.
5. Con la URL pública, poner `SELF_URL=https://<esa-url>` como variable de
   entorno del servicio y repetir la prueba de `/chat` — ahí sí se prueba el
   round-trip completo (front → proxy → Claude → MCP → datos → respuesta).
6. Widget de chat en el front, apuntando a esa URL ya desplegada.
7. (Futuro, no bloqueante) migrar la fuente de datos del MCP de
   parquet/JSON a Postgres, si `pipeline/load_postgres.py` llega a
   construirse.

## Decisiones que faltan por tomar en equipo

- **Historial de conversación:** ¿vive solo en el navegador (se manda
  completo en cada request) o se guarda sesión en el servidor? Empezar por
  lo simple (solo navegador) hasta que el volumen de contexto lo justifique.
- **Rate limiting de `/chat`:** es una API paga (Anthropic) expuesta
  indirectamente al público a través del tablero.
- **Gemini queda fuera de este plan v1.** El connector directo de MCP en la
  API de Claude no tiene un equivalente igual de simple documentado para
  Gemini; si se quiere soportar Gemini más adelante, el proxy tendría que
  correr su propio loop de tool-calling contra el mismo servidor MCP en vez
  de delegárselo a la API como con Claude.
