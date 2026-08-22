# Plomada conversacional: MCP + Claude en el tablero

Plan de implementación para que cualquier IA (Claude, y a futuro Gemini) pueda
responder preguntas sobre los datos de Plomada **conversando desde el
tablero**, en vez de solo mirando gráficos y tablas. Este documento es para
el equipo y para quien trabaje el front — no requiere leer el resto del
código para entender qué construir y en qué orden.

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

### 1. Servidor MCP — `api/app/mcp/`

SDK oficial de Python (`mcp`), transporte HTTP (Claude necesita una URL
pública a la que llamar, no `stdio`). Revisar la documentación del SDK al
implementar para la forma exacta de montarlo como sub-ruta de la app FastAPI
existente — no está fijada aquí a propósito, para no prescribir una API que
no se ha verificado contra el SDK instalado.

Tools propuestas (cada una una consulta DuckDB acotada, con `LIMIT` explícito
para no volcar tablas completas al contexto del modelo):

| Tool | Qué responde | Fuente |
|---|---|---|
| `resumen_indicios` | Cifras titulares (contratos atípicos, plata en riesgo) | `web/data/titulares.json`, `meta.json` |
| `buscar_contratos_atipicos(entidad?, departamento?, tipo_contrato?, min_valor?, limit=20)` | Lista de contratos marcados, con sus banderas | `base.parquet` / `puntajes` |
| `perfil_entidad(nit_o_nombre)` | Resumen de una entidad: contratos, valor, banderas, autosupervisión | `base.parquet`, `web/data/departamentos.json` |
| `buscar_proveedor(nombre_o_doc)` | Red del proveedor: cluster, si hace obra e interventoría, contratos | `web/data/red.json` |
| `alertas_preadjudicacion(entidad?, solo_con_alerta=true, limit=20)` | Procesos abiertos con banderas pre-adjudicación | `web/data/alertas.json` |

Reparte estas tools entre los dueños de cada pilar (quien escribió
`06_banderas_grafo.sql` sabe mejor qué exponer en `perfil_entidad`/
`buscar_proveedor`, quien escribió `alertas.py` sabe qué exponer en
`alertas_preadjudicacion`, etc.) — no hace falta que una sola persona
entienda todo el warehouse para escribir su tool.

### 2. Proxy de chat — extiende `api/app/main.py`

- `POST /chat`, recibe `{mensaje, historial?}`.
- Llama a la Messages API de Claude con:
  ```
  mcp_servers: [{ type: "url", url: "<url pública del propio servicio>/mcp", name: "plomada" }]
  tools:       [{ type: "mcp_toolset", mcp_server_name: "plomada" }]
  ```
  más el beta header `mcp-client-2025-11-20`. Las dos partes son obligatorias:
  mandar `mcp_servers` sin el `tools` correspondiente lo rechaza la API.
- `ANTHROPIC_API_KEY` vive como variable de entorno en Render — **nunca** en
  el front ni en el repo.
- Responde en streaming (SSE) para que el chat se sienta vivo, no que
  aparezca todo de un bloque al final.

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

## Orden de trabajo sugerido

1. Servidor MCP corriendo local, probado con el inspector de MCP o con
   Claude Code apuntando a `localhost` — sin proxy ni front todavía.
2. **Ojo con esto:** Claude llama al MCP server desde la nube de Anthropic,
   así que `localhost` no sirve para probar el connector remoto completo.
   Hace falta un túnel (ngrok, Cloudflare Tunnel) o ya desplegar un ambiente
   de prueba antes de poder probar `/chat` de punta a punta.
3. Endpoint `/chat` en `api/`, probado con curl/Postman contra el MCP (local
   con túnel, o ya desplegado).
4. Deploy a Render — un solo servicio sirviendo `/chat` y `/mcp`.
5. Widget de chat en el front, apuntando al Render ya desplegado.
6. (Futuro, no bloqueante) migrar la fuente de datos del MCP de
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
