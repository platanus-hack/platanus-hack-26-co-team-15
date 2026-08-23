"""Geocodifica out/contratos_atipicos.csv a geo/geocache.json.

Offline y desechable, igual que gen_synthetic.py: corre una vez (o cuando
cambien los datos), cachea en disco, y build.py despues solo LEE ese cache.
build.py nunca golpea la red — asi el sitio se genera igual de rapido si el
proveedor de geocodificacion esta caido, y las pruebas no dependen de internet.

Cascada de fallback (misma que INSTRUCCIONES_AGENTE_GEOCODIFICACION.md):
  1. Nominatim con la direccion exacta
  2. ArcGIS con la direccion exacta (mejor tolerancia a vias rurales)
  3. ArcGIS con solo el municipio (cabecera municipal)
  4. Centro de Colombia — pero build.py NUNCA pinta este fallback en un mapa,
     ver data.coords_contrato().

Requiere geopy en un venv, no en el Python del sistema:
    python3 -m venv .venv && .venv/bin/pip install geopy
    .venv/bin/python geocode.py
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import data as D

DEFECTO = {"lat": 4.570868, "lon": -74.297333, "precision": "defecto"}
ESPERA = 1.0  # seg entre llamadas reales. Politica de uso de Nominatim, no negociable.


def geocodificar(query, intentos):
    """intentos: [(nombre_precision, geolocator), ...] en orden de preferencia."""
    for nombre, geolocator in intentos:
        try:
            time.sleep(ESPERA)
            loc = geolocator.geocode(query, timeout=10)
            if loc:
                return {"lat": loc.latitude, "lon": loc.longitude, "precision": nombre}
        except Exception:
            continue
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None,
                    help="geocodificar como maximo N entradas nuevas (para probar sin esperar todo)")
    ap.add_argument("--solo-cabecera", action="store_true",
                    help="saltar el intento de direccion exacta, ir directo a cabecera municipal. "
                         "ponytail: a escala real (78k contratos) la direccion rural rara vez "
                         "geocodifica exacto y el intento exacto es el que domina el tiempo total; "
                         "esta bandera lo salta. Subir a intento exacto de nuevo si hace falta precision de calle.")
    ap.add_argument("--reintentar-defecto", action="store_true",
                    help="reintentar cabeceras municipales que la ultima vez cayeron al centro de Colombia")
    args = ap.parse_args()

    try:
        from geopy.geocoders import ArcGIS, Nominatim
    except ImportError:
        sys.exit("Falta geopy. Corra: python3 -m venv .venv && .venv/bin/pip install geopy\n"
                 "y ejecute este script con .venv/bin/python, no con el python del sistema.")

    filas = D.leer_csv("contratos_atipicos.csv")
    if not filas:
        sys.exit(f"{D.OUT}/contratos_atipicos.csv vacio. Corra primero gen_synthetic.py o el pipeline real.")

    cache = D.cargar_geocache()
    osm, arcgis = Nominatim(user_agent="plomada_agent/1.0"), ArcGIS()

    exactas_pend, municipios_pend = {}, {}
    for r in filas:
        exacta, clave_mun = D.claves_geocodificacion(r.get("dir_ejecucion"), r.get("ciudad"), r.get("departamento"))
        if not clave_mun:
            continue  # sin municipio confiable (p.ej. 'NO DEFINIDO'): no hay donde centrar nada
        if not args.solo_cabecera and exacta and exacta not in cache["exacta"]:
            exactas_pend[exacta] = True
        actual = cache["municipio"].get(clave_mun)
        if actual is None or (args.reintentar_defecto and actual.get("precision") == "defecto"):
            municipios_pend[clave_mun] = tuple(clave_mun.split("|", 1))

    total = len(exactas_pend) + len(municipios_pend)
    if not total:
        print(f"geo/geocache.json ya cubre todo {D.OUT}/contratos_atipicos.csv. Nada que hacer.")
        return
    print(f"{len(exactas_pend)} direcciones exactas y {len(municipios_pend)} cabeceras "
          f"municipales por geocodificar (~{total} seg de espera minima).")

    hechos = 0
    for exacta in exactas_pend:
        if args.limit is not None and hechos >= args.limit:
            break
        r = geocodificar(exacta, [("exacta_osm", osm), ("exacta_arcgis", arcgis)])
        if r:
            cache["exacta"][exacta] = r
        hechos += 1
        if hechos % 20 == 0:
            D.guardar_geocache(cache)
            print(f"  {hechos}/{total} — guardado parcial")
    D.guardar_geocache(cache)

    for clave_mun, (dep, ciu) in municipios_pend.items():
        if args.limit is not None and hechos >= args.limit:
            break
        r = geocodificar(f"{ciu}, {dep}, Colombia", [("cabecera_municipal", arcgis)])
        cache["municipio"][clave_mun] = r or DEFECTO
        hechos += 1
        if hechos % 20 == 0:
            D.guardar_geocache(cache)
            print(f"  {hechos}/{total} — guardado parcial")
    D.guardar_geocache(cache)

    resueltas = sum(1 for v in cache["municipio"].values() if v["precision"] != "defecto")
    print(f"listo: {hechos} geocodificaciones nuevas. "
          f"{resueltas}/{len(cache['municipio'])} municipios con ubicacion real "
          f"(el resto cayo al defecto y no se muestra en ningun mapa).")


def demo():
    """Autochequeo sin red: la logica de claves y el filtro de 'defecto'."""
    assert D.claves_geocodificacion("KM 1 VIA X", "NO DEFINIDO", "CHOCO") == (None, None)
    assert D.claves_geocodificacion("", "EL BAGRE", "ANTIOQUIA")[0] is None
    exacta, mun = D.claves_geocodificacion("KM 1 VIA X", "EL BAGRE", "ANTIOQUIA")
    assert exacta == "KM 1 Via X, El Bagre, Antioquia, Colombia", exacta
    assert mun == "Antioquia|El Bagre", mun

    cache = {"exacta": {}, "municipio": {"Antioquia|El Bagre": DEFECTO}}
    fila = {"dir_ejecucion": "KM 1 VIA X", "ciudad": "EL BAGRE", "departamento": "ANTIOQUIA"}
    assert D.coords_contrato(fila, cache) is None, "el fallback 'defecto' no deberia pintar mapa"

    cache["municipio"]["Antioquia|El Bagre"] = {"lat": 7.6, "lon": -74.8, "precision": "cabecera_municipal"}
    assert D.coords_contrato(fila, cache)["precision"] == "cabecera_municipal"
    print("demo(): ok")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        demo()
    else:
        main()
