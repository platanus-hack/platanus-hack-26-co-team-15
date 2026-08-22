"""Puertas de calidad de datos. Fallan el PR, no son advertencias.

Cada test de aqui existe porque el error correspondiente YA ocurrio en este
proyecto y produjo numeros falsos. No borrar ninguno sin entender cual.

    pytest tests/ -v
"""
from __future__ import annotations

import os

import duckdb
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "warehouse", "plomada.duckdb")

# Cifras de referencia medidas el 2026-08-22 contra datos.gov.co.
# Crecen con el tiempo (SECOP II sigue publicando), por eso son pisos.
MIN_CONTRATOS = 77_000
MIN_VALOR_COP = 190e12          # ~$190 billones
MAX_VALOR_COP = 400e12          # techo de cordura
TECHO_VALOR_CONTRATO = 1e13     # 10 billones COP por contrato


@pytest.fixture(scope="module")
def con():
    if not os.path.exists(DB):
        pytest.skip("no hay warehouse; corre 'python pipeline/build.py'")
    c = duckdb.connect(DB, read_only=True)
    yield c
    c.close()


def tablas(con):
    return {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}


# ---------------------------------------------------------------------------
# 1. Fan-out de join.
# El dataset de procesos trae varias filas por proceso (una por lote y por
# adjudicacion). Unir directo duplica contratos y contamina TODOS los conteos.
# ---------------------------------------------------------------------------
def test_base_no_duplica_contratos(con):
    n_contratos = con.execute("SELECT count(*) FROM contratos").fetchone()[0]
    n_base = con.execute("SELECT count(*) FROM base").fetchone()[0]
    assert n_base == n_contratos, (
        "base tiene %d filas y contratos %d: el join contra procesos hizo fan-out. "
        "procesos_1x debe colapsar a una fila por notice_uid ANTES de unir."
        % (n_base, n_contratos)
    )


def test_id_contrato_es_unico(con):
    dup = con.execute(
        "SELECT count(*) FROM (SELECT id_contrato FROM base GROUP BY 1 HAVING count(*) > 1)"
    ).fetchone()[0]
    assert dup == 0, "%d id_contrato repetidos en base" % dup


# ---------------------------------------------------------------------------
# 2. Banderas imposibles.
# Dos banderas dieron 0% para siempre por razones estructurales, no por
# ausencia de riesgo: el tope de anticipo del 50% lo impone la plataforma, y
# 'pagado + pendiente = valor' es una identidad contable.
# Una bandera en 0% o en 100% no informa nada y hay que rediseniarla.
# ---------------------------------------------------------------------------
def test_ninguna_bandera_esta_muerta(con):
    banderas = [r[0] for r in con.execute("SELECT bandera FROM pesos").fetchall()]
    total = con.execute("SELECT count(*) FROM puntajes").fetchone()[0]
    muertas, saturadas = [], []
    for b in banderas:
        n = con.execute(
            "SELECT sum(coalesce(%s::INT, 0)) FROM puntajes" % b
        ).fetchone()[0] or 0
        if n == 0:
            muertas.append(b)
        elif n == total:
            saturadas.append(b)
    assert not muertas, (
        "banderas que nunca se disparan (revisa si la condicion es posible): %s" % muertas
    )
    assert not saturadas, "banderas que se disparan siempre (no discriminan): %s" % saturadas


def test_toda_bandera_tiene_peso_y_glosa(con):
    faltan = con.execute(
        "SELECT bandera FROM pesos WHERE peso IS NULL OR glosa IS NULL OR glosa = ''"
    ).fetchall()
    assert not faltan, "banderas sin peso o sin glosa publicable: %s" % faltan


# ---------------------------------------------------------------------------
# 3. Valores imposibles.
# 24 contratos vienen publicados con cifras de hasta 6e18 COP (mas que el PIB
# mundial) y entre ellos concentraban el 98,6% del "total" agregado.
# Se aislan, no se borran; y ninguna suma de dinero los incluye.
# ---------------------------------------------------------------------------
def test_valor_plausible_excluye_imposibles(con):
    fuera = con.execute(
        "SELECT count(*) FROM base WHERE valor_plausible > %f" % TECHO_VALOR_CONTRATO
    ).fetchone()[0]
    assert fuera == 0, "%d contratos con valor_plausible sobre el techo" % fuera


def test_valor_total_en_rango_de_cordura(con):
    total = con.execute("SELECT sum(valor_plausible) FROM base").fetchone()[0]
    assert MIN_VALOR_COP < total < MAX_VALOR_COP, (
        "valor total = %.3e COP, fuera del rango esperado. Si subio de golpe, "
        "revisa que las sumas usen valor_plausible y no valor." % total
    )


def test_los_imposibles_quedan_marcados(con):
    marcados = con.execute(
        "SELECT sum(coalesce(f_valor_implausible::INT, 0)) FROM puntajes"
    ).fetchone()[0]
    reales = con.execute(
        "SELECT count(*) FROM base WHERE valor IS NOT NULL AND valor_plausible IS NULL"
    ).fetchone()[0]
    assert marcados == reales, "%d valores imposibles pero %d marcados" % (reales, marcados)


# ---------------------------------------------------------------------------
# 4. Cobertura minima.
# ---------------------------------------------------------------------------
def test_cobertura_del_universo(con):
    n = con.execute("SELECT count(*) FROM base").fetchone()[0]
    assert n >= MIN_CONTRATOS, "solo %d contratos; la ingesta quedo incompleta" % n


def test_join_contrato_proceso_no_se_rompio(con):
    """Las llaves nativas estan en namespaces distintos (CO1.BDOS vs CO1.REQ) y
    no cruzan. El puente es el noticeUID de la URL publica, que daba 99,6%."""
    pct = con.execute(
        "SELECT 100.0 * count(*) FILTER (WHERE precio_base IS NOT NULL) / count(*) FROM base"
    ).fetchone()[0]
    assert pct > 90, (
        "solo %.1f%% de contratos unidos a su proceso (esperado ~99,6%%). "
        "El join debe ser por notice_uid, no por proceso_de_compra." % pct
    )


# ---------------------------------------------------------------------------
# 5. Llaves placeholder que crean cliques falsos.
# domicilio_replegal es 63% 'NO DEFINIDO' y liga 19.403 proveedores. Usado
# como arista crea UN clique de 19.403 nodos que se traga el grafo.
# ---------------------------------------------------------------------------
def test_ningun_cluster_gigante(con):
    if "clusters" not in tablas(con):
        pytest.skip("el grafo aun no esta construido")
    mayor = con.execute(
        "SELECT max(n) FROM (SELECT count(*) n FROM clusters GROUP BY cluster_id)"
    ).fetchone()[0]
    assert mayor <= 200, (
        "el clúster mas grande tiene %d proveedores: una llave placeholder se "
        "filtro a las aristas. Revisa llaves_basura." % mayor
    )


def test_red_cuentas_separa_ruido_de_senal(con):
    """Las Juntas de Accion Comunal comparten cuenta por canalizacion de pagos
    municipales, no por cartel. Y la cuenta de un consorcio suele estar a
    nombre del lider. Solo 'empresas_independientes' es indicio."""
    tipos = {r[0] for r in con.execute("SELECT DISTINCT tipo_red FROM red_cuentas").fetchall()}
    assert "empresas_independientes" in tipos, "red_cuentas perdio la clasificacion tipo_red"
    n = con.execute(
        "SELECT count(*) FROM red_cuentas WHERE tipo_red = 'comunitaria'"
    ).fetchone()[0]
    marcadas = con.execute(
        """SELECT count(*) FROM puntajes p JOIN base b USING (id_contrato)
           JOIN red_cuentas r USING (cuenta_key)
           WHERE r.tipo_red = 'comunitaria' AND p.f_cuenta_compartida"""
    ).fetchone()[0]
    assert marcadas == 0, (
        "%d contratos de redes comunitarias marcados como cuenta compartida "
        "(hay %d grupos comunitarios que deben quedar excluidos)" % (marcadas, n)
    )


# ---------------------------------------------------------------------------
# 6. Privacidad.
# La cuenta bancaria se usa como llave de union interna y JAMAS se publica.
# ---------------------------------------------------------------------------
def test_el_snapshot_publico_no_lleva_cuentas(con):
    """base.parquet se comparte entre frentes; las vistas de serving (90-99)
    son las que van al API y esas no pueden llevar la cuenta."""
    for t in tablas(con):
        if not t.startswith("api_"):
            continue
        cols = {
            r[0]
            for r in con.execute(
                "SELECT column_name FROM duckdb_columns() WHERE table_name = ?", [t]
            ).fetchall()
        }
        filtradas = cols & {"cuenta_key", "n_mero_de_cuenta", "numero_de_cuenta"}
        assert not filtradas, "la vista de serving %s expone %s" % (t, filtradas)


# ---------------------------------------------------------------------------
# 7. Capa de grafo (04-06).
# ---------------------------------------------------------------------------
def test_lista_negra_atrapa_el_placeholder_gigante(con):
    """'NO DEFINIDO' en domicilio_replegal liga 19.403 proveedores. Si se
    escapa, produce un solo clique que se traga el grafo entero."""
    if "llaves_basura" not in tablas(con):
        pytest.skip("el grafo aun no esta construido")
    n = con.execute(
        """SELECT count(*) FROM llaves_basura
           WHERE tipo_llave = 'domicilio' AND upper(valor) = 'NO DEFINIDO'"""
    ).fetchone()[0]
    assert n == 1, "'NO DEFINIDO' no esta en la lista negra de domicilios"


def test_ninguna_arista_usa_llave_negra(con):
    if "aristas_prov" not in tablas(con):
        pytest.skip("el grafo aun no esta construido")
    fugas = con.execute(
        """SELECT count(*) FROM aristas_prov a
           JOIN llaves_basura k ON k.valor = a.llave
           WHERE (a.tipo = 'comparte_cuenta'    AND k.tipo_llave = 'cuenta')
              OR (a.tipo = 'comparte_domicilio' AND k.tipo_llave = 'domicilio')
              OR (a.tipo = 'comparte_replegal'  AND k.tipo_llave = 'replegal')"""
    ).fetchone()[0]
    assert fugas == 0, "%d aristas construidas sobre llaves de la lista negra" % fugas


def test_banderas_de_red_no_estan_muertas(con):
    if "pesos_grafo" not in tablas(con):
        pytest.skip("la capa de grafo aun no esta construida")
    total = con.execute("SELECT count(*) FROM riesgo_total").fetchone()[0]
    for (b,) in con.execute("SELECT bandera FROM pesos_grafo").fetchall():
        n = con.execute(
            "SELECT sum(coalesce(%s::INT, 0)) FROM riesgo_total" % b
        ).fetchone()[0] or 0
        assert 0 < n < total, "bandera de red %s no discrimina (%d de %d)" % (b, n, total)


def test_riesgo_total_no_duplica(con):
    if "banderas_grafo" not in tablas(con):
        pytest.skip("la capa de grafo aun no esta construida")
    n_base = con.execute("SELECT count(*) FROM base").fetchone()[0]
    n_rt = con.execute("SELECT count(*) FROM riesgo_total").fetchone()[0]
    assert n_rt == n_base, "riesgo_total tiene %d filas y base %d" % (n_rt, n_base)


def test_autosupervision_separa_costumbre_de_anomalia(con):
    """En algunas entidades autosupervisar es el 92-100% de lo que firman:
    eso es costumbre administrativa, no 240 fallas individuales. La bandera
    de contrato solo debe marcar donde es la excepcion."""
    if "tasa_autosupervision" not in tablas(con):
        pytest.skip("no construido")
    mal = con.execute(
        """SELECT count(*) FROM puntajes p
           JOIN tasa_autosupervision t USING (nit_entidad)
           WHERE p.f_ordenador_es_supervisor AND t.tasa >= 0.5"""
    ).fetchone()[0]
    assert mal == 0, (
        "%d contratos marcados en entidades donde autosupervisar es la norma; "
        "esos van a entidades_autosupervision, no a la bandera" % mal
    )


# ---------------------------------------------------------------------------
# 8. Alertas pre-adjudicacion (30 + pipeline/alertas.py).
# ---------------------------------------------------------------------------
def test_alertas_no_duplica_procesos(con):
    if "alertas" not in tablas(con):
        pytest.skip("alertas aun no se ha corrido")
    n_raw = con.execute(
        "SELECT count(DISTINCT id_del_proceso) FROM abiertos_raw"
    ).fetchone()[0]
    n_alertas = con.execute("SELECT count(*) FROM alertas").fetchone()[0]
    assert n_alertas == n_raw, (
        "alertas tiene %d filas y abiertos_raw %d ids distintos: el dedup "
        "por id_del_proceso se rompio" % (n_alertas, n_raw)
    )


def test_universo_clasifica_todo(con):
    """85,5% del snapshot no tiene fecha de cierre y 12,9% la tiene vencida.
    Mezclar eso con lo accionable (1,6%) inflaria el titular de forma
    enganosa. Todo registro debe caer en exactamente una categoria."""
    if "alertas" not in tablas(con):
        pytest.skip("alertas aun no se ha corrido")
    sin_clasificar = con.execute(
        "SELECT count(*) FROM alertas WHERE universo NOT IN "
        "('accionable','zombie_vencido','sin_fecha_cierre')"
    ).fetchone()[0]
    assert sin_clasificar == 0, "%d procesos sin universo asignado" % sin_clasificar


def test_solo_accionables_tienen_dias_restantes_positivos(con):
    if "alertas" not in tablas(con):
        pytest.skip("alertas aun no se ha corrido")
    mal = con.execute(
        "SELECT count(*) FROM alertas WHERE universo = 'zombie_vencido' "
        "AND dias_restantes >= 0"
    ).fetchone()[0]
    assert mal == 0, "%d procesos marcados vencidos con dias_restantes >= 0" % mal


def test_primera_corrida_no_inventa_addenda(con):
    """Sin snapshot anterior, f_cierre_movido debe quedar NULL (no False):
    NULL dice 'no hay con que comparar', False diria 'no cambio', que
    seria una afirmacion falsa el primer dia."""
    if "alertas" not in tablas(con):
        pytest.skip("alertas aun no se ha corrido")
    hay_ayer = con.execute("SELECT count(*) FROM abiertos_ayer").fetchone()[0]
    if hay_ayer > 0:
        pytest.skip("ya hay snapshot anterior; no es la primera corrida")
    no_nulos = con.execute(
        "SELECT count(*) FROM alertas WHERE f_cierre_movido IS NOT NULL"
    ).fetchone()[0]
    assert no_nulos == 0, (
        "%d filas con f_cierre_movido distinto de NULL sin snapshot anterior" % no_nulos
    )


# ---------------------------------------------------------------------------
# 9. urlproceso: Socrata lo publica como STRUCT(url VARCHAR), no como texto.
# CAST(struct AS VARCHAR) produce la representacion "{'url': '...'}" en vez
# de la URL, lo que rompe cualquier enlace clicable en reportes, CSVs y el
# tablero. El bug estuvo presente desde el primer commit (afectaba a 'base'
# y 'atipicos') sin romper el join, porque el regex de notice_uid encontraba
# el patron igual dentro del texto mal formado.
# ---------------------------------------------------------------------------
def test_urlproceso_es_una_url_no_un_struct(con):
    malformados = con.execute(
        "SELECT count(*) FROM base WHERE urlproceso IS NOT NULL "
        "AND urlproceso NOT LIKE 'http%'"
    ).fetchone()[0]
    assert malformados == 0, (
        "%d urlproceso no empiezan por 'http': probablemente volvio el "
        "CAST(urlproceso AS VARCHAR) sobre el STRUCT(url VARCHAR) crudo "
        "en vez de usar urlproceso.url" % malformados
    )
