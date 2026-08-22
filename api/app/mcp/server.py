"""Servidor MCP de Plomada: tools de solo lectura sobre los datos ya
publicados, para que Claude (u otra IA con soporte de MCP) pueda responder
preguntas conversacionales desde el tablero. Ver MCP.md en la raiz del repo
para el plan completo.

Lee directo de `data/exports/base.parquet`/`puntajes.parquet` (el contrato
de datos de solo lectura entre frentes, ver pipeline/build.py) y de los JSON
en `web/data/` que ya genera `pipeline/export_web.py`. No toca Postgres ni
`pipeline/load_postgres.py`: eso es una migracion futura de donde leen las
tools, no del contrato de las tools en si.

Requiere Python >=3.10 (el SDK oficial de `mcp` lo exige). El resto del
pipeline esta fijado a Python 3.9 en el entorno local, por eso este servidor
vive con su propio entorno (ver api/requirements.txt).

Correr en local (stdio, para probar con un cliente MCP o el inspector):
    python -m api.app.mcp.server

Correr como servidor HTTP (lo que necesita el connector remoto de Claude):
    python -m api.app.mcp.server --http --port 8765
"""
from __future__ import annotations

import json
import os
import sys

import duckdb
from mcp.server import MCPServer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
EXPORTS = os.path.join(ROOT, "data", "exports")
WEB_DATA = os.path.join(ROOT, "web", "data")
BASE_PARQUET = os.path.join(EXPORTS, "base.parquet").replace("\\", "/")
PUNTAJES_PARQUET = os.path.join(EXPORTS, "puntajes.parquet").replace("\\", "/")

LIMIT_DURO = 50  # ningun tool devuelve mas filas que esto, sin importar lo que pida el modelo

mcp = MCPServer(
    name="plomada",
    title="Plomada: riesgo en contratacion de obra publica (SECOP II)",
    instructions=(
        "Datos publicos de contratacion de obra publica en Colombia (SECOP II). "
        "'Riesgo' aqui significa indicio para priorizar investigacion periodistica "
        "y control social, NUNCA prueba de fraude. No afirmes que un contrato "
        "marcado es corrupto: di que presenta indicios y cuales son."
    ),
)


def _consultar(sql, params=None):
    con = duckdb.connect(":memory:", read_only=False)
    try:
        return con.execute(sql, params or []).fetchdf().to_dict(orient="records")
    finally:
        con.close()


def _leer_json(nombre):
    with open(os.path.join(WEB_DATA, nombre), "r", encoding="utf-8") as fh:
        return json.load(fh)


@mcp.tool()
def resumen_indicios() -> dict:
    """Cifras titulares del proyecto: contratos analizados, plata en riesgo
    por categoria de indicio, y las limitaciones que hay que decir en voz
    alta (cobertura de datos, que NO se puede afirmar). Usa esto primero
    para dar contexto antes de responder preguntas puntuales."""
    titulares = _leer_json("titulares.json")
    meta = _leer_json("meta.json")
    return {"titulares": titulares, "limitaciones": meta.get("limitaciones", [])}


@mcp.tool()
def buscar_contratos_atipicos(
    entidad: str | None = None,
    departamento: str | None = None,
    tipo_contrato: str | None = None,
    valor_minimo: float | None = None,
    limite: int = 20,
) -> list[dict]:
    """Busca contratos marcados como atipicos (indicio fuerte, o 6+ puntos
    acumulados de banderas mas debiles). Filtros opcionales por entidad
    (coincidencia parcial), departamento, tipo_contrato (OBRA/INTERVENTORIA/
    CONSULTORIA/CONCESION/ASOCIACION PUBLICO PRIVADA) y valor minimo en COP.
    Devuelve como maximo 50 filas aunque se pida mas."""
    limite = max(1, min(limite, LIMIT_DURO))
    condiciones = ["(n_banderas_fuertes >= 1 OR puntos_crudos >= 6)"]
    params = []
    if entidad:
        condiciones.append("entidad ILIKE ?")
        params.append("%%%s%%" % entidad)
    if departamento:
        condiciones.append("departamento ILIKE ?")
        params.append("%%%s%%" % departamento)
    if tipo_contrato:
        condiciones.append("tipo_contrato = ?")
        params.append(tipo_contrato.upper())
    if valor_minimo:
        condiciones.append("valor_plausible >= ?")
        params.append(valor_minimo)
    sql = """
        SELECT id_contrato, entidad, departamento, ciudad, tipo_contrato, modalidad,
               valor_plausible, n_banderas_fuertes, puntos_crudos, proveedor,
               anio, urlproceso
        FROM read_parquet(?)
        WHERE %s
        ORDER BY n_banderas_fuertes DESC, puntos_crudos DESC, valor_plausible DESC
        LIMIT ?
    """ % " AND ".join(condiciones)
    return _consultar(sql, [PUNTAJES_PARQUET] + params + [limite])


@mcp.tool()
def perfil_entidad(nombre_o_nit: str) -> dict:
    """Resumen de una entidad contratante: cuantos contratos tiene, cuanto
    ha adjudicado, y cuantos de sus contratos estan marcados como atipicos.
    Recibe el nombre (coincidencia parcial) o el NIT exacto."""
    sql = """
        SELECT
          any_value(entidad)                                          AS entidad,
          any_value(nit_entidad)                                      AS nit_entidad,
          any_value(departamento)                                     AS departamento,
          count(*)                                                    AS n_contratos,
          sum(valor_plausible)                                        AS valor_total,
          sum((n_banderas_fuertes >= 1 OR puntos_crudos >= 6)::INT)    AS n_atipicos
        FROM read_parquet(?)
        WHERE nit_entidad = ? OR entidad ILIKE ?
        GROUP BY nit_entidad
        ORDER BY n_contratos DESC
        LIMIT 5
    """
    filas = _consultar(sql, [PUNTAJES_PARQUET, nombre_o_nit, "%%%s%%" % nombre_o_nit])
    if not filas:
        return {"encontrado": False, "mensaje": "Ninguna entidad coincide con '%s'" % nombre_o_nit}
    return {"encontrado": True, "coincidencias": filas}


def main():
    if "--http" in sys.argv:
        port = 8765
        if "--port" in sys.argv:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        mcp.run(transport="streamable-http", port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
