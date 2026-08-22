"""Genera los reportes de Plomada desde el warehouse.

Uso:  python src/report.py
Salida: CSVs en out/ + resumen por consola.
"""
from __future__ import annotations

import os

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "warehouse", "plomada.duckdb")
OUT = os.path.join(ROOT, "out")

MILLON = 1e6
MILLARDO = 1e9


def money(x):
    if x is None:
        return "-"
    if abs(x) >= 1e12:
        return "$%.2f billones" % (x / 1e12)
    if abs(x) >= MILLARDO:
        return "$%.1f mil millones" % (x / MILLARDO)
    return "$%.0f millones" % (x / MILLON)


def show(con, title, sql, limit=15):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)
    rel = con.sql(sql)
    rel.limit(limit).show(max_width=200, max_rows=limit + 2)
    return rel


def main():
    os.makedirs(OUT, exist_ok=True)
    con = duckdb.connect(DB, read_only=True)

    # ---------- cobertura y sanidad del join ----------
    print("=" * 78)
    print("COBERTURA")
    print("=" * 78)
    cov = con.execute(
        """
        SELECT
          count(*)                                             AS contratos,
          sum(valor_plausible)                                 AS valor_total,
          count(*) FILTER (WHERE valor IS NOT NULL AND valor_plausible IS NULL) AS valor_imposible,
          count(*) FILTER (WHERE precio_base IS NOT NULL)       AS con_proceso,
          count(*) FILTER (WHERE n_oferentes_unicos IS NOT NULL) AS con_dato_oferentes,
          count(*) FILTER (WHERE doc_ordenador IS NOT NULL)     AS con_ordenador,
          count(*) FILTER (WHERE doc_supervisor IS NOT NULL)    AS con_supervisor,
          count(*) FILTER (WHERE cuenta_key IS NOT NULL)        AS con_cuenta,
          count(*) FILTER (WHERE dir_ejecucion IS NOT NULL)     AS con_direccion
        FROM base
        """
    ).fetchone()
    labels = ["contratos", "valor total", "con valor IMPOSIBLE", "con proceso unido",
              "con dato de oferentes", "con cedula de ordenador",
              "con cedula de supervisor", "con cuenta bancaria",
              "con direccion de ejecucion"]
    for lab, v in zip(labels, cov):
        if lab == "valor total":
            print("  %-28s %s" % (lab, money(v)))
        else:
            pct = 100.0 * v / cov[0] if cov[0] else 0
            print("  %-28s %9d  (%.1f%%)" % (lab, v, pct))

    # ---------- que tan seguido se enciende cada bandera ----------
    banderas = [r[0] for r in con.execute("SELECT bandera FROM pesos").fetchall()]
    parts = ["count(*) AS n_total"]
    for b in banderas:
        parts.append("sum(coalesce(%s::INT,0)) AS %s" % (b, b))
    row = con.execute("SELECT %s FROM puntajes" % ", ".join(parts)).fetchdf().iloc[0]
    print("\n" + "=" * 78)
    print("FRECUENCIA DE CADA BANDERA")
    print("=" * 78)
    tot = int(row["n_total"])
    freq = sorted(((b, int(row[b])) for b in banderas), key=lambda t: -t[1])
    for b, n in freq:
        glosa = con.execute("SELECT glosa FROM pesos WHERE bandera=?", [b]).fetchone()[0]
        print("  %-27s %7d  %5.1f%%  %s" % (b, n, 100.0 * n / tot, glosa))

    atip = con.execute("SELECT count(*) FILTER (WHERE es_atipico), sum(CASE WHEN es_atipico THEN valor_plausible END) FROM atipicos").fetchone()
    print("\n  CONTRATOS ATIPICOS: %d de %d (%.1f%%)  |  valor: %s"
          % (atip[0], tot, 100.0 * atip[0] / tot, money(atip[1])))

    # ---------- rankings ----------
    show(con, "MUNICIPIOS con mayor tasa ajustada de contratos atipicos (min. 20 contratos)",
         """SELECT ciudad, departamento, n_contratos, n_atipicos,
                   round(tasa_cruda*100,1) AS pct_crudo,
                   round(tasa_ajustada*100,1) AS pct_ajustado,
                   round(valor_atipico/1e9,1) AS mil_millones_atipicos,
                   n_proponente_unico, n_obra_directa, n_fraccionamiento
            FROM ranking_municipios WHERE n_contratos >= 20
            ORDER BY tasa_ajustada DESC""", 20)

    show(con, "ADMINISTRACIONES con mayor tasa ajustada (entidad x periodo, min. 20 contratos)",
         """SELECT entidad, ciudad, periodo_gobierno, n_contratos, n_atipicos,
                   round(tasa_ajustada*100,1) AS pct_ajustado,
                   round(valor_atipico/1e9,1) AS mil_millones_atipicos
            FROM ranking_administraciones WHERE n_contratos >= 20
            ORDER BY tasa_ajustada DESC""", 20)

    show(con, "DEPARTAMENTOS",
         """SELECT departamento, n_contratos, n_atipicos,
                   round(tasa_ajustada*100,1) AS pct_ajustado,
                   round(valor_atipico/1e9,1) AS mil_millones_atipicos
            FROM ranking_departamentos WHERE n_contratos >= 50
            ORDER BY tasa_ajustada DESC""", 20)

    show(con, "REDES: cuentas bancarias compartidas por proveedores distintos",
         """SELECT n_proveedores, len(proveedores) AS n_nombres, proveedores
            FROM red_cuentas ORDER BY n_proveedores DESC""", 12)

    show(con, "REDES: representantes legales en varias empresas proveedoras",
         """SELECT nombre, n_proveedores, proveedores
            FROM red_replegal ORDER BY n_proveedores DESC""", 12)

    show(con, "ORDENADORES DEL GASTO mas concentrados (>=10 proveedores, alto HHI)",
         """SELECT v.nombre, v.n_contratos, v.n_entidades,
                   round(v.valor_total/1e9,1) AS mil_millones,
                   round(p.share_top1*100,1) AS pct_a_su_top1,
                   round(p.hhi,3) AS hhi
            FROM perfil_ordenador p JOIN vol_ordenador v USING (doc_ordenador)
            WHERE p.n_proveedores >= 10
            ORDER BY p.hhi DESC""", 15)

    show(con, "CONTRATOS DE MAYOR RIESGO (banderas fuertes + valor)",
         """SELECT entidad, ciudad, round(valor_plausible/1e9,2) AS mil_millones,
                   tipo_contrato, modalidad, n_banderas_fuertes, puntos_crudos,
                   proveedor, anio, urlproceso
            FROM atipicos
            WHERE es_atipico AND valor_plausible > 1e9
            ORDER BY n_banderas_fuertes DESC, valor DESC""", 20)

    # ---------- exportes ----------
    exports = {
        "ranking_municipios.csv": "SELECT * FROM ranking_municipios",
        "ranking_administraciones.csv": "SELECT * FROM ranking_administraciones",
        "ranking_departamentos.csv": "SELECT * FROM ranking_departamentos",
        "contratos_atipicos.csv": "SELECT * FROM atipicos WHERE es_atipico",
        "banderas_glosario.csv": "SELECT * FROM pesos ORDER BY peso DESC, bandera",
    }
    print("\n" + "=" * 78)
    print("EXPORTES")
    print("=" * 78)
    for fname, sql in exports.items():
        path = os.path.join(OUT, fname).replace("\\", "/")
        con.execute("COPY (%s) TO '%s' (HEADER, DELIMITER ',')" % (sql, path))
        n = con.execute("SELECT count(*) FROM (%s)" % sql).fetchone()[0]
        print("  out/%-32s %7d filas" % (fname, n))

    con.close()


if __name__ == "__main__":
    main()
