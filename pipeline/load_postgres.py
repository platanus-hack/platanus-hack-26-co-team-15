"""Carga a Postgres el subconjunto de datos que necesita la capa de serving
(api/app/mcp/server.py). No es el warehouse completo: solo lo que hoy
consumen las tools del MCP. Agregar una tabla nueva es una linea mas en
`TABLAS`, mismo patron.

Por que DuckDB y no pandas/sqlalchemy: ya es dependencia de pipeline/, y su
extension `postgres` permite escribir directo desde parquet/JSON a Postgres
en una sola sentencia SQL, sin pasar los datos por un DataFrame intermedio.

Requiere:
    python pipeline/build.py             (para data/exports/puntajes.parquet)
    python pipeline/export_web.py        (para web/data/titulares.json y meta.json)
    DATABASE_URL en el entorno, apuntando al Postgres de destino
    (postgresql://usuario:clave@host:puerto/basededatos)
"""
from __future__ import annotations

import json
import os
import sys

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUNTAJES = os.path.join(ROOT, "data", "exports", "puntajes.parquet").replace("\\", "/")
TITULARES = os.path.join(ROOT, "web", "data", "titulares.json").replace("\\", "/")
META = os.path.join(ROOT, "web", "data", "meta.json")


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        sys.exit("falta DATABASE_URL en el entorno (postgresql://usuario:clave@host:puerto/db)")
    for path in (PUNTAJES, TITULARES, META):
        if not os.path.exists(path):
            sys.exit(
                "falta %s; corre 'python pipeline/build.py' y "
                "'python pipeline/export_web.py' primero" % path
            )

    con = duckdb.connect(":memory:")
    con.execute("INSTALL postgres")
    con.execute("LOAD postgres")
    con.execute("ATTACH '%s' AS pg (TYPE POSTGRES)" % database_url)

    print(">> puntajes", flush=True)
    con.execute("CREATE OR REPLACE TABLE pg.puntajes AS SELECT * FROM read_parquet('%s')" % PUNTAJES)
    n = con.execute("SELECT count(*) FROM pg.puntajes").fetchone()[0]
    print("   %d filas" % n)

    print(">> titulares", flush=True)
    con.execute(
        "CREATE OR REPLACE TABLE pg.titulares AS SELECT * FROM read_json_auto('%s')" % TITULARES
    )
    n = con.execute("SELECT count(*) FROM pg.titulares").fetchone()[0]
    print("   %d filas" % n)

    # meta.json es chico y de forma variable (cobertura, limitaciones...): se
    # guarda el blob completo como texto en vez de normalizarlo en columnas.
    # json.loads() en el lado que lo lee (api/app/mcp/server.py).
    print(">> meta", flush=True)
    with open(META, "r", encoding="utf-8") as fh:
        meta_texto = fh.read()
    con.execute("CREATE OR REPLACE TABLE pg.meta (id INTEGER, datos VARCHAR)")
    con.execute("INSERT INTO pg.meta VALUES (1, ?)", [meta_texto])
    print("   1 fila")

    con.close()
    print("\nCargado en Postgres: puntajes, titulares, meta")


if __name__ == "__main__":
    main()
