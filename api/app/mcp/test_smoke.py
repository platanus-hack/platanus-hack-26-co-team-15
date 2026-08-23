"""Prueba de humo manual del servidor MCP -- no es parte de la suite de
pytest del pipeline (ese vive en Python 3.9; esto exige >=3.10).

    python -m venv .venv-mcp && .venv-mcp/Scripts/pip install -r api/requirements.txt
    .venv-mcp/Scripts/python api/app/mcp/test_smoke.py          # via stdio
    .venv-mcp/Scripts/python api/app/mcp/server.py --http &     # via http
    .venv-mcp/Scripts/python api/app/mcp/test_smoke.py --http
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


async def probar(session):
    info = await session.initialize()
    print("conectado a:", info.server_info.name)

    tools = await session.list_tools()
    print("tools:", [t.name for t in tools.tools])
    assert {"resumen_indicios", "buscar_contratos_atipicos", "perfil_entidad"} <= {
        t.name for t in tools.tools
    }

    r = await session.call_tool("resumen_indicios", {})
    data = json.loads(r.content[0].text)
    assert data["titulares"], "resumen_indicios no trajo titulares"
    print("resumen_indicios: OK (%d titulares)" % len(data["titulares"]))

    r = await session.call_tool(
        "buscar_contratos_atipicos", {"departamento": "CUNDINAMARCA", "limite": 3}
    )
    assert len(r.content) == 3
    print("buscar_contratos_atipicos: OK (%d filas)" % len(r.content))

    r = await session.call_tool("perfil_entidad", {"nombre_o_nit": "bogota"})
    data = json.loads(r.content[0].text)
    assert data["encontrado"]
    print("perfil_entidad('bogota'): OK (%d coincidencias)" % len(data["coincidencias"]))

    r = await session.call_tool("perfil_entidad", {"nombre_o_nit": "esto-no-existe-en-secop"})
    data = json.loads(r.content[0].text)
    assert not data["encontrado"]
    print("perfil_entidad(inexistente): OK (reporta no encontrado, no inventa datos)")


async def main():
    if "--http" in sys.argv:
        async with streamable_http_client("http://127.0.0.1:8765/mcp") as (read, write):
            async with ClientSession(read, write) as session:
                await probar(session)
    else:
        params = StdioServerParameters(
            command=sys.executable, args=[os.path.join(ROOT, "api", "app", "mcp", "server.py")]
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await probar(session)
    print("\nTODO OK")


if __name__ == "__main__":
    asyncio.run(main())
