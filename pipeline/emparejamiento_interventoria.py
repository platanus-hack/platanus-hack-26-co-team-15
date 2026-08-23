"""Empareja cada interventoria con la obra que vigila, POR CONTRATO.

Cierra "A4": sql/06_banderas_grafo.sql y pipeline/grafo.py ya detectan a
nivel de PROVEEDOR que interventor y constructor son la misma red; esto
dice ademas QUE interventoria vigila QUE obra especifica.

Requiere: python pipeline/build.py --steps 07 --no-export

Por que esto no es solo SQL: la similitud de texto (TF-IDF + coseno) no es
expresable en DuckDB de forma confiable. Se probo jaccard() nativo
(q-gramas de caracteres) y da falsos positivos graves entre objetos de
obra que no tienen nada que ver, solo por compartir vocabulario comun del
sector ("CONSTRUCCION", "MUNICIPIO", "MEJORAMIENTO"...): dos objetos
claramente distintos puntuaban 0,69. TF-IDF (ya es dependencia del
proyecto) resuelve esto bajando el peso de esas palabras de cajon. Mismo
patron estructural que pipeline/grafo.py con Louvain: el algoritmo vive en
Python, sql/07_candidatos_interventoria.sql solo prepara los insumos.

La fecha de firma NO se usa como filtro duro: medido contra los matches de
citacion explicita con score alto, el 18% esta a mas de 2 anios de
distancia (entidades reusan el mismo objeto en contratos de mantenimiento
recurrente). Se reporta como columna informativa, no como filtro.

CANDIDATOS, NO CONFIRMADOS. No hay ground truth para fijar un umbral de
precision todavia: el equipo tiene que etiquetar a mano la muestra que
este script exporta en out/muestra_validacion_interventoria.csv antes de
que estos matches cuenten como evidencia publicable o entren a una
bandera puntuada en 06_banderas_grafo.sql.
"""
from __future__ import annotations

import os
import sys

import duckdb
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "warehouse", "plomada.duckdb")
OUT = os.path.join(ROOT, "out")

SEED = 20260822   # misma semilla que grafo.py: muestra reproducible
MAX_DF = 0.3      # baja el peso de palabras de cajon del sector
MIN_DF = 2        # descarta errores de tipeo que aparecen una sola vez
TRUNCAR = 200      # objeto se trunca para que la tabla sea legible sin el CSV


def cargar(con):
    tablas = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    faltan = {"obras_para_emparejar", "interventorias_para_emparejar"} - tablas
    if faltan:
        sys.exit(
            "faltan tablas (%s); corre "
            "'python pipeline/build.py --steps 07 --no-export' primero" % faltan
        )
    obras = con.execute("SELECT * FROM obras_para_emparejar").fetchdf()
    interv = con.execute("SELECT * FROM interventorias_para_emparejar").fetchdf()
    return obras, interv


def emparejar(obras, interv):
    vec = TfidfVectorizer(max_df=MAX_DF, min_df=MIN_DF)
    x_obra = vec.fit_transform(obras["objeto"])
    texto_consulta = interv["citado"].where(interv["tiene_cita"], interv["objeto"])
    x_int = vec.transform(texto_consulta)

    idx_por_entidad = obras.groupby("nit_entidad").indices

    filas = []
    for pos in range(len(interv)):
        nit = interv["nit_entidad"].iat[pos]
        cand = idx_por_entidad.get(nit)
        fila = {
            "id_interventoria": interv["id_contrato"].iat[pos],
            "nit_entidad": nit,
            "entidad": interv["entidad"].iat[pos],
            "metodo": "citacion_explicita" if interv["tiene_cita"].iat[pos] else "similitud_texto",
            "objeto_interventoria": str(interv["objeto"].iat[pos])[:TRUNCAR],
            "id_obra": None, "score": None,
            "dias_diferencia_firma": None, "objeto_obra": None,
            "id_obra_alt1": None, "score_alt1": None,
            "id_obra_alt2": None, "score_alt2": None,
        }
        if cand is not None and len(cand):
            # clip: cosine_similarity puede pasarse de 1.0 por error de
            # redondeo de punto flotante en matches casi identicos.
            sims = np.clip(cosine_similarity(x_int[pos], x_obra[cand])[0], 0.0, 1.0)
            orden = np.argsort(-sims)[:3]
            top = cand[orden[0]]
            fila["id_obra"] = obras["id_contrato"].iat[top]
            fila["score"] = float(sims[orden[0]])
            fila["objeto_obra"] = str(obras["objeto"].iat[top])[:TRUNCAR]
            f_i, f_o = interv["fecha_firma"].iat[pos], obras["fecha_firma"].iat[top]
            if pd.notna(f_i) and pd.notna(f_o):
                fila["dias_diferencia_firma"] = (f_i - f_o).days
            for slot, oi in zip(("alt1", "alt2"), orden[1:]):
                if sims[oi] > 0:
                    fila["id_obra_%s" % slot] = obras["id_contrato"].iat[cand[oi]]
                    fila["score_%s" % slot] = float(sims[oi])
        filas.append(fila)
    return pd.DataFrame(filas)


def exportar_muestra(df, path):
    """Hasta ~100 filas estratificadas por metodo y banda de score, para
    que el equipo llene 'correcto' a mano. Sin esto ningun umbral de score
    puede afirmarse confiable: no hay con que medirlo todavia."""
    con_candidato = df[df["score"].notna()].copy()
    con_candidato["banda"] = pd.cut(
        con_candidato["score"], bins=[0, 0.3, 0.6, 1.01],
        labels=["bajo", "medio", "alto"], right=False,
    )
    partes = []
    for _, grupo in con_candidato.groupby("metodo"):
        for _, sub in grupo.groupby("banda", observed=True):
            partes.append(sub.sample(min(len(sub), 17), random_state=SEED))
    muestra = pd.concat(partes) if partes else con_candidato.head(0)
    muestra = muestra.drop(columns="banda")
    muestra["correcto"] = ""
    muestra["notas"] = ""
    cols = ["id_interventoria", "entidad", "metodo", "score",
            "objeto_interventoria", "objeto_obra", "id_obra",
            "dias_diferencia_firma", "id_obra_alt1", "score_alt1",
            "id_obra_alt2", "score_alt2", "correcto", "notas"]
    muestra[cols].to_csv(path, index=False, encoding="utf-8")
    return len(muestra)


def main():
    if not os.path.exists(DB):
        sys.exit("no hay warehouse; corre 'python pipeline/build.py' primero")
    os.makedirs(OUT, exist_ok=True)
    con = duckdb.connect(DB)

    obras, interv = cargar(con)
    print("obras candidatas: %d   interventorias a emparejar: %d" % (len(obras), len(interv)))

    df = emparejar(obras, interv)

    con.execute("DROP TABLE IF EXISTS emparejamiento_interventoria")
    con.register("df_emparejamiento", df[[
        "id_interventoria", "nit_entidad", "entidad", "id_obra", "metodo",
        "score", "dias_diferencia_firma", "objeto_interventoria", "objeto_obra",
    ]])
    con.execute("CREATE TABLE emparejamiento_interventoria AS SELECT * FROM df_emparejamiento")
    con.unregister("df_emparejamiento")

    n = len(df)
    con_cita = int((df["metodo"] == "citacion_explicita").sum())
    con_candidato = int(df["score"].notna().sum())
    sin_candidato = n - con_candidato
    print("\n%-28s %6d  (%.1f%%)" % ("con cita explicita", con_cita, 100.0 * con_cita / n))
    print("%-28s %6d  (%.1f%%)" % ("con algun candidato", con_candidato, 100.0 * con_candidato / n))
    print("%-28s %6d  (%.1f%%)" % ("sin ninguna obra candidata", sin_candidato, 100.0 * sin_candidato / n))
    if con_candidato:
        print("\nscore del mejor candidato: mediana %.2f, p10 %.2f, p90 %.2f"
              % (df["score"].median(), df["score"].quantile(.1), df["score"].quantile(.9)))

    path = os.path.join(OUT, "muestra_validacion_interventoria.csv")
    n_muestra = exportar_muestra(df, path)
    print("\nmuestra de validacion: %d filas -> out/muestra_validacion_interventoria.csv" % n_muestra)
    print(
        "\nCANDIDATOS SIN VALIDAR. Antes de usarlos como evidencia publicable o de\n"
        "sumarlos a una bandera puntuada, llena la columna 'correcto' (SI/NO) en\n"
        "ese CSV a mano y mide la precision real por metodo y banda de score."
    )
    con.close()


if __name__ == "__main__":
    main()
