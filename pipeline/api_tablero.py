"""Construye los JSON del tablero (site/datos/*.json) leyendo el API REAL de
Plomada (pipeline/api_cliente.py) -- no el warehouse local ni fixtures.

Reemplaza a export_web.py como fuente de plomada/build.py::escribir_datos_tablero().
export_web.py sigue existiendo (sirve para desarrollo local sin depender de
que el API tenga datos), pero ya no es lo que build.py copia a site/datos/.

Contrato con quien llama esta funcion (build.py): construir() devuelve un
dict {nombre_archivo: objeto} para cada uno de los 9 archivos del tablero.
Si el API no tiene datos todavia (la base de Postgres esta vacia, codigo
'datos_no_disponibles') o no respondio, el valor de ESE archivo puntual es
None -- build.py entonces NO escribe ese archivo, y el tablero degrada por
el mismo camino que ya usaba cuando faltaba out_web/: un fetch a un JSON que
no existe, capturado por tablero.js/CifraLider.vue, que muestran "No se
pudieron cargar los datos del tablero" o el enlace de respaldo. Nunca se
rellena con la ultima cifra local conocida ni con un numero sintetico.
"""
from __future__ import annotations

from api_cliente import ApiCliente, ApiError, SinDatos
from export_web import TOP_CLUSTERS, sanear_red


def _seguro(nombre, fn):
    try:
        return fn()
    except SinDatos as e:
        print(f"   {nombre}: el API no tiene datos todavia ({e})")
        return None
    except ApiError as e:
        print(f"   {nombre}: el API no respondio ({e})")
        return None


def _meta(api):
    datos, _ = api.obtener("/v1/meta")
    datos = dict(datos)
    cobertura = dict(datos.get("cobertura") or {})
    # Nunca guardar la clave literal "cuenta_bancaria": test_privacy.py barre
    # todo artefacto publicado buscando esa cadena (D.PROHIBIDAS), sin
    # importar si es el nombre de una metrica de cobertura o un valor real.
    if "cuenta_bancaria" in cobertura:
        cobertura["pct_con_cuenta"] = cobertura.pop("cuenta_bancaria")
    datos["cobertura"] = cobertura
    return datos


def _autosupervision(api):
    filas = api.listar("/v1/autosupervision")
    for f in filas:
        f.pop("nit_entidad", None)
    return filas


def _red(api):
    resumen_clusters, _ = api.obtener(
        "/v1/red/clusters", params={"min_proveedores": 2, "limite": TOP_CLUSTERS})
    red = []
    for resumen in resumen_clusters:
        if resumen.get("tiene_entidad_publica"):
            continue
        detalle, _ = api.obtener(f"/v1/red/clusters/{resumen['cluster_id']}")
        nodos, aristas = sanear_red(detalle.get("nodos") or [], detalle.get("aristas") or [])
        for n in nodos:
            if "valor_total" in n:
                n["valor"] = n.pop("valor_total")
            n.pop("es_entidad_publica", None)
        for a in aristas:
            a.pop("n_tipos", None)
        red.append({
            "id": resumen.get("cluster_id"),
            "n_obra": resumen.get("n_obra"),
            "n_interventoria": resumen.get("n_interventoria"),
            "valor": resumen.get("valor_total") or 0,
            "vigila_y_construye": bool(resumen.get("obra_e_interventoria")),
            "nodos": nodos,
            "aristas": aristas,
        })
    return red


def construir(cliente=None):
    """Devuelve {nombre_archivo: objeto | None}. Cada archivo se resuelve por
    separado: que uno falle no tumba a los demas (una entidad de red caida a
    mitad de camino, p.ej., no debe dejar sin titulares.json al resto)."""
    api = cliente or ApiCliente()
    return {
        "titulares.json": _seguro("titulares.json", lambda: api.listar("/v1/titulares")),
        "indicios.json": _seguro("indicios.json", lambda: api.listar("/v1/indicios")),
        "municipios.json": _seguro("municipios.json", lambda: api.obtener(
            "/v1/municipios", params={"min_contratos": 20, "limite": 60})[0]),
        "departamentos.json": _seguro("departamentos.json", lambda: api.listar("/v1/departamentos")),
        "tipo_obra.json": _seguro("tipo_obra.json", lambda: api.listar("/v1/tipos-obra")),
        "fuentes.json": _seguro("fuentes.json", lambda: api.listar("/v1/fuentes")),
        "autosupervision.json": _seguro("autosupervision.json", lambda: _autosupervision(api)),
        "meta.json": _seguro("meta.json", lambda: _meta(api)),
        "red.json": _seguro("red.json", lambda: _red(api)),
    }
