"""Exporta el warehouse a JSON estatico para el tablero web.

Uso:  python pipeline/export_web.py
Salida: web/data/*.json

Sin API ni build step: el tablero es un solo HTML que lee estos archivos.
Es un prototipo funcional que el equipo puede portar a Next.js despues; la
forma de los JSON es a proposito la misma que tendran los endpoints
(/titulares, /municipios, /departamentos, /red).
"""
from __future__ import annotations

import json
import os

import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "warehouse", "plomada.duckdb")
OUT = os.path.join(ROOT, "web", "data")

TOP_CLUSTERS = 40


def rows(con, sql, params=None):
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def write(name, obj):
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    print("   %-26s %7.1f KB" % (name, os.path.getsize(path) / 1024))


def main():
    os.makedirs(OUT, exist_ok=True)
    con = duckdb.connect(DB, read_only=True)
    print("exportando a web/data/")

    write("titulares.json", rows(con, """
        SELECT concepto, n_contratos, coalesce(valor, 0) AS valor FROM titulares"""))

    write("indicios.json", rows(con, """
        SELECT indicio, grupo, n_contratos, coalesce(valor, 0) AS valor
        FROM plata_por_indicio ORDER BY valor DESC"""))

    # Municipios: se llevan las DOS tasas para poder mostrar el efecto del
    # encogimiento bayesiano en un dumbbell. Esa comparacion es el argumento
    # metodologico y no se puede esconder.
    write("municipios.json", rows(con, """
        SELECT ciudad, departamento, n_contratos, n_atipicos,
               tasa_cruda, tasa_ajustada,
               coalesce(valor_total, 0) AS valor_total,
               coalesce(valor_atipico, 0) AS valor_atipico,
               n_proponente_unico, n_obra_directa, n_fraccionamiento
        FROM ranking_municipios
        WHERE n_contratos >= 20
        ORDER BY tasa_ajustada DESC LIMIT 60"""))

    write("departamentos.json", rows(con, """
        SELECT d.departamento, d.n_contratos,
               coalesce(d.total, 0) AS total,
               coalesce(d.sin_competencia, 0) AS sin_competencia,
               coalesce(d.en_riesgo, 0) AS en_riesgo,
               coalesce(d.regalias, 0) AS regalias,
               r.tasa_ajustada
        FROM plata_por_departamento d
        LEFT JOIN ranking_departamentos r USING (departamento)
        ORDER BY d.total DESC"""))

    write("tipo_obra.json", rows(con, """
        SELECT tipo_obra, n_contratos, coalesce(total,0) AS total,
               coalesce(en_riesgo,0) AS en_riesgo,
               coalesce(sin_competencia,0) AS sin_competencia
        FROM plata_por_tipo_obra ORDER BY total DESC"""))

    write("fuentes.json", rows(con, """
        SELECT fuente, total, en_riesgo FROM plata_por_fuente ORDER BY total DESC"""))

    write("autosupervision.json", rows(con, """
        SELECT entidad, departamento, ciudad, n_auto, n_con_ambos, tasa,
               coalesce(valor_auto, 0) AS valor_auto
        FROM entidades_autosupervision ORDER BY valor_auto DESC"""))

    # ---- Red: un subgrafo por cluster, solo los mas relevantes ----
    ids = [r["cluster_id"] for r in rows(con, """
        SELECT cluster_id FROM clusters_perfil
        WHERE n_proveedores > 1 AND NOT tiene_entidad_publica
        ORDER BY (obra_e_interventoria::INT) DESC, valor_total DESC
        LIMIT %d""" % TOP_CLUSTERS)]

    red = []
    for cid in ids:
        nodos = rows(con, """
            SELECT p.doc, p.nombre, p.n_obra, p.n_interventoria, p.n_contratos,
                   coalesce(p.valor_total, 0) AS valor, p.n_entidades
            FROM clusters c JOIN nodos_proveedor p ON p.doc = c.doc_proveedor
            WHERE c.cluster_id = ?
            ORDER BY p.valor_total DESC""", [cid])
        docs = {n["doc"] for n in nodos}
        aristas = [
            {"a": a["doc_a"], "b": a["doc_b"], "peso": a["peso"], "tipos": list(a["tipos"])}
            for a in rows(con, """
                SELECT doc_a, doc_b, peso, tipos FROM aristas_prov_1x
                WHERE doc_a IN (SELECT doc_proveedor FROM clusters WHERE cluster_id = ?)
                  AND doc_b IN (SELECT doc_proveedor FROM clusters WHERE cluster_id = ?)""",
                [cid, cid])
            if a["doc_a"] in docs and a["doc_b"] in docs
        ]
        perfil = rows(con, "SELECT * FROM clusters_perfil WHERE cluster_id = ?", [cid])[0]
        red.append({
            "id": cid,
            "n_obra": perfil["n_obra"],
            "n_interventoria": perfil["n_interventoria"],
            "valor": perfil["valor_total"] or 0,
            "vigila_y_construye": bool(perfil["obra_e_interventoria"]),
            "nodos": nodos,
            "aristas": aristas,
        })
    write("red.json", red)

    # Metadatos: cobertura y limitaciones viajan CON los datos, para que el
    # tablero no pueda mostrar una cifra sin su salvedad al lado.
    cov = con.execute("""
        SELECT count(*), sum(valor_plausible),
               count(*) FILTER (WHERE doc_ordenador IS NOT NULL),
               count(*) FILTER (WHERE doc_supervisor IS NOT NULL),
               count(*) FILTER (WHERE cuenta_key IS NOT NULL),
               count(*) FILTER (WHERE precio_base IS NOT NULL)
        FROM base""").fetchone()
    write("meta.json", {
        "contratos": cov[0],
        "valor_total": cov[1],
        "cobertura": {
            "cedula_ordenador": cov[2] / cov[0],
            "cedula_supervisor": cov[3] / cov[0],
            "cuenta_bancaria": cov[4] / cov[0],
            "unido_a_proceso": cov[5] / cov[0],
        },
        "n_clusters": con.execute("SELECT count(*) FROM clusters_perfil").fetchone()[0],
        "limitaciones": [
            "Riesgo no es fraude: son indicios para priorizar investigacion.",
            "Solo SECOP II. No incluye SECOP I ni entidades que publican mal.",
            "La cedula del ordenador del gasto esta en el 64,5% de los contratos y la del supervisor en el 54,3%: el analisis de red cubre esa fraccion.",
            "La cuenta bancaria esta en el 23,7%: las redes detectadas son un piso, no un censo.",
            "No hay datos de oferentes perdedores, solo el numero de ofertas y el ganador.",
            "El sobrecosto por unidad fisica no es calculable: solo el 0,9% de las descripciones declara una cantidad con unidad.",
            "El ranking municipal no esta normalizado por poblacion.",
        ],
    })
    con.close()


if __name__ == "__main__":
    main()
