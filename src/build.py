"""Construye el warehouse DuckDB a partir de los JSONL crudos.

Uso:  python src/build.py
Salida: data/warehouse/plomada.duckdb  +  reportes CSV en out/
"""
from __future__ import annotations

import glob
import os
import sys
import time

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
SQL = os.path.join(ROOT, "sql")
DB = os.path.join(ROOT, "data", "warehouse", "plomada.duckdb")

STEPS = ["01_stage.sql", "02_flags.sql", "03_ranking.sql"]


def run_sql_file(con, path):
    with open(path, "r", encoding="utf-8") as fh:
        sql = fh.read()
    # las rutas de los JSONL se inyectan aqui para que el SQL sea portable
    sql = sql.replace("__RAW__", RAW.replace("\\", "/"))
    con.execute(sql)


def main():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    for folder in ("contratos", "procesos"):
        files = glob.glob(os.path.join(RAW, folder, "*.jsonl"))
        if not files:
            sys.exit("falta la ingesta: no hay JSONL en data/raw/%s" % folder)
        print("%s: %d archivos" % (folder, len(files)))

    con = duckdb.connect(DB)
    con.execute("SET preserve_insertion_order=false")

    for step in STEPS:
        t0 = time.time()
        print("\n>> %s" % step, flush=True)
        run_sql_file(con, os.path.join(SQL, step))
        print("   ok (%.1fs)" % (time.time() - t0), flush=True)

    for tbl in ("contratos", "procesos", "base", "flags", "puntajes"):
        n = con.execute("SELECT count(*) FROM %s" % tbl).fetchone()[0]
        print("%-12s %8d filas" % (tbl, n))

    con.close()
    print("\nwarehouse -> %s" % DB)


if __name__ == "__main__":
    main()
