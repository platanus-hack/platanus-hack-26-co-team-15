"""Servidor MCP de Plomada: tools de solo lectura sobre los datos ya
publicados, para que Claude (u otra IA con soporte de MCP) pueda responder
preguntas conversacionales desde el tablero. Ver MCP.md en la raiz del repo
para el plan completo.

Lee de Postgres (`DATABASE_URL`), cargado por `pipeline/load_postgres.py`
desde `data/exports/puntajes.parquet` y `web/data/*.json`. No lee archivos
locales: esos estan en .gitignore y no viajan con la imagen de Docker que se
despliega en Render, asi que la fuente de datos en produccion tiene que ser
una base de datos, no el filesystem del contenedor.

Requiere Python >=3.10 (el SDK oficial de `mcp` lo exige). El resto del
pipeline esta fijado a Python 3.9 en el entorno local, por eso este servidor
vive con su propio entorno (ver api/requirements.txt).

Correr en local (stdio, para probar con un cliente MCP o el inspector):
    DATABASE_URL=postgresql://plomada:plomada@localhost:5432/plomada python -m api.app.mcp.server

Correr como servidor HTTP (lo que necesita el connector remoto de Claude):
    python -m api.app.mcp.server --http --port 8765
"""
from __future__ import annotations

import json
import os
import sys

import psycopg
from mcp.server import MCPServer
from psycopg.rows import dict_row

LIMIT_DURO = 50  # ningun tool devuelve mas filas que esto, sin importar lo que pida el modelo


def _database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        # RuntimeError, no sys.exit(): esto corre dentro de un tool handler de
        # un servidor de larga duracion -- sys.exit() tumbaria el proceso
        # entero en la primera pregunta sin DATABASE_URL, no solo esa llamada.
        raise RuntimeError(
            "falta DATABASE_URL en el entorno; corre 'python pipeline/load_postgres.py' "
            "contra un Postgres y apunta esta variable ahi"
        )
    return url


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
    with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


@mcp.tool()
def resumen_indicios() -> dict:
    """Cifras titulares del proyecto: contratos analizados, plata en riesgo
    por categoria de indicio, y las limitaciones que hay que decir en voz
    alta (cobertura de datos, que NO se puede afirmar). Usa esto primero
    para dar contexto antes de responder preguntas puntuales."""
    titulares = _consultar("SELECT * FROM titulares")
    meta_filas = _consultar("SELECT datos FROM meta WHERE id = 1")
    meta = json.loads(meta_filas[0]["datos"]) if meta_filas else {}
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
        condiciones.append("entidad ILIKE %s")
        params.append("%%%s%%" % entidad)
    if departamento:
        condiciones.append("departamento ILIKE %s")
        params.append("%%%s%%" % departamento)
    if tipo_contrato:
        condiciones.append("tipo_contrato = %s")
        params.append(tipo_contrato.upper())
    if valor_minimo:
        condiciones.append("valor_plausible >= %s")
        params.append(valor_minimo)
    sql = """
        SELECT id_contrato, entidad, departamento, ciudad, tipo_contrato, modalidad,
               valor_plausible, n_banderas_fuertes, puntos_crudos, proveedor,
               anio, urlproceso
        FROM puntajes
        WHERE %s
        ORDER BY n_banderas_fuertes DESC, puntos_crudos DESC, valor_plausible DESC
        LIMIT %%s
    """ % " AND ".join(condiciones)
    return _consultar(sql, params + [limite])


@mcp.tool()
def perfil_entidad(nombre_o_nit: str) -> dict:
    """Resumen de una entidad contratante: cuantos contratos tiene, cuanto
    ha adjudicado, y cuantos de sus contratos estan marcados como atipicos.
    Recibe el nombre (coincidencia parcial) o el NIT exacto."""
    # any_value() requiere Postgres >=16 (docker-compose.yml ya usa postgres:16-alpine)
    sql = """
        SELECT
          any_value(entidad)                                          AS entidad,
          nit_entidad,
          any_value(departamento)                                     AS departamento,
          count(*)                                                    AS n_contratos,
          sum(valor_plausible)                                        AS valor_total,
          sum((n_banderas_fuertes >= 1 OR puntos_crudos >= 6)::INT)    AS n_atipicos
        FROM puntajes
        WHERE nit_entidad = %s OR entidad ILIKE %s
        GROUP BY nit_entidad
        ORDER BY n_contratos DESC
        LIMIT 5
    """
    filas = _consultar(sql, [nombre_o_nit, "%%%s%%" % nombre_o_nit])
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
