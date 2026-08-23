"""Genera el sitio estatico en site/.

Estatico a proposito: cada contrato, municipio y busqueda tiene una URL real
y compartible, el HTML sale ya renderizado (indexable) y no hay servidor que
mantener. Los 78.000 contratos caben en un portatil.
"""
import csv, html, json, shutil, sys
from collections import defaultdict
from pathlib import Path

import contenido as C
import data as D

RAIZ = Path(__file__).parent
SITE = RAIZ / "site"
# pipeline/export_web.py escribe aqui (Tanda A, A4): build.py es lo UNICO
# que escribe site/, para que test_privacy.py controle todo el artefacto
# publicado de una sola pasada. Si no existe (no se corrio export_web.py,
# o no hay warehouse), el tablero simplemente no trae esos JSON -- no es
# fatal, ver copiar_datos_tablero().
OUT_WEB = RAIZ.parent / "out_web"
SITIO_NOMBRE = "Plomada"
LEMA = "Indicios de irregularidad en la contratacion de obra publica en Colombia"

# Leaflet vendorizado (Tanda B, B6): plomada/static/vendor/leaflet/, version
# 1.9.4, licencia BSD-2 (ver design/VENDOR.md). Nada de unpkg en produccion.
LEAFLET_CSS = '<link rel="stylesheet" href="/static/vendor/leaflet/leaflet.css">'
LEAFLET_JS = '<script src="/static/vendor/leaflet/leaflet.js"></script>'


def h(x):
    return html.escape(str(x if x is not None else ""), quote=True)


# ------------------------------------------------------------- nav (B1)
# Las ocho vistas (portada, tablero, mapa, buscador, metodologia, datos,
# ficha de contrato, ficha de municipio) pasan TODAS por pagina(): un solo
# shell, un solo <nav>. Adopta .nav + .nav-brand de Modernist (readme.md,
# componente "navigation"): el brand va primero y con margin-right:auto
# empuja los enlaces a la derecha, todos hijos directos de .nav para que el
# gap de Modernist quede parejo entre ellos -- envolverlos en un <nav>
# interior (como antes) les habria dejado sin espaciado, porque el gap de
# Modernist solo aplica entre hijos DIRECTOS.
NAV_ENLACES = (
    ("/tablero/", "Tablero"), ("/mapa/", "Mapa"), ("/buscar/", "Buscador"),
    ("/metodologia/", "Metodologia"), ("/datos/", "Datos"),
)


def nav(ruta_actual):
    enlaces = "".join(
        f'<a href="{h(u)}"{" aria-current=\"page\"" if ruta_actual.rstrip("/") == u.rstrip("/") else ""}>{h(t)}</a>'
        for u, t in NAV_ENLACES)
    return f'<header class="nav"><a class="nav-brand" href="/">Plomada</a>{enlaces}</header>'


# --------------------------------------------------------- islas de Vue (T1)
# docs/PLAN_VUE.md §4.3. build.py no aprende nada de Vue: solo emite un
# <div data-isla="..."> con un fallback pre-renderizado adentro (nunca
# vacio) y, una vez por pagina, el script del bundle. El bundle vive en
# plomada/static/vendor/islas/ (COMMITEADO, ver design/VENDOR.md) para que
# entre a site/ por el copytree de main() y siga habiendo un unico escritor.
ISLAS_JS = '<script type="module" src="/static/vendor/islas/islas.js"></script>'


def isla(nombre, fallback="", **props):
    """Contenedor de una isla de Vue. `fallback` es lo que ve un lector sin
    JS y lo que lee plomada/test_privacy.py: nunca se deja vacio. La isla lo
    *reemplaza* al montar, nunca lo *crea* de la nada."""
    attrs = "".join(f' data-{k.replace("_", "-")}="{h(v)}"' for k, v in props.items())
    return f'<div data-isla="{h(nombre)}"{attrs}>{fallback}</div>'


def aviso_fijo(texto, enlace=("Que significa esto", "/metodologia/")):
    """El aviso permanente ('Indicio, no acusacion') como bloque reutilizable
    (B1): antes vivia copiado a mano solo en la ficha de contrato. Se usa en
    toda vista que muestre una cifra agregada o una ficha individual, para
    que la salvedad este siempre donde hay un numero que se pueda malleer."""
    texto_enlace, url_enlace = enlace
    return (f'<div class="aviso-fijo" role="note"><strong>Indicio, no acusacion.</strong> '
            f'{texto} <a href="{h(url_enlace)}">{h(texto_enlace)}</a></div>')


# ----------------------------------------------------------------- plantilla
def pagina(titulo, descripcion, cuerpo, ruta, head="", js="", clase=""):
    canon = "/" + ruta if not ruta.startswith("/") else ruta
    return f"""<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{h(titulo)} — {SITIO_NOMBRE}</title>
<meta name="description" content="{h(descripcion)}">
<link rel="canonical" href="{h(canon)}">
<meta property="og:title" content="{h(titulo)} — {SITIO_NOMBRE}">
<meta property="og:description" content="{h(descripcion)}">
<meta property="og:type" content="article">
<link rel="stylesheet" href="/static/estilo.css">
{head}
<body class="{clase}">
<a class="saltar" href="#principal">Saltar al contenido</a>
{nav(canon)}
<main id="principal">
{cuerpo}
</main>
<footer class="pie">
  <p class="aviso">{C.AVISO}</p>
  <p>Datos publicos del SECOP II. <a href="/metodologia/">Como se calcula</a> ·
     <a href="/datos/">Descargar los datos</a></p>
</footer>
{js}
"""


def escribir(ruta, contenido_html):
    destino = SITE / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido_html, encoding="utf-8")


def migas(*pares):
    partes = []
    for texto, url in pares:
        partes.append(f'<a href="{h(url)}">{h(texto)}</a>' if url else f"<span>{h(texto)}</span>")
    return '<nav class="migas" aria-label="Ruta">' + " / ".join(partes) + "</nav>"


def dato(etiqueta, valor, extra=""):
    return (f'<div class="dato"><dt>{h(etiqueta)}</dt>'
            f'<dd>{valor}{extra}</dd></div>')


# ------------------------------------------------------------------- 7.1 ficha
def url_contrato(c):
    return f"/contrato/{D.slug(c['id_contrato'])}/"


def url_municipio(dep, ciu):
    return f"/municipio/{D.slug(dep, ciu)}/"


def barra_score(c):
    s = c.get("score") or 0
    fuertes = c.get("n_banderas_fuertes") or 0
    return f"""<div class="score">
  <div class="score-num"><b>{fuertes}</b> <span>senal{'' if fuertes == 1 else 'es'} fuerte{'' if fuertes == 1 else 's'}</span></div>
  <div class="score-bar" role="img" aria-label="Puntaje {D._num(s, 2)} de 1">
    <i style="width:{min(100, s * 100):.0f}%"></i></div>
  <div class="score-pie">Puntaje {D._num(s, 2)} / 1 &middot; suma de pesos, no una probabilidad.
    <a href="/metodologia/#puntaje">Como se calcula</a></div>
</div>"""


def bloque_banderas(grupos, total):
    if not total:
        return '<p class="vacio">Este contrato no tiene senales encendidas.</p>'
    out = []
    for grupo, items in grupos:
        out.append(f'<section class="grupo"><h3>{h(grupo)}</h3>')
        for b in items:
            aten = " atenuada" if b["atenuada"] else ""
            etq = ('<span class="etq-aten" title="Patron esperable en este contexto: '
                   'no cuenta como indicio fuerte">senal atenuada</span>') if b["atenuada"] else ""
            ev = (f'<p class="evidencia"><span>Evidencia</span> {h(b["evidencia"])}</p>'
                  if b["evidencia"] else
                  '<p class="evidencia sin"><span>Evidencia</span> sin dato numerico '
                  'para esta bandera en este contrato</p>')
            out.append(f"""<article class="bandera{aten}">
  <h4>{h(D.titulo(b["bandera"].removeprefix("f_").replace("_", " ")))}
      <span class="peso" title="Peso de la bandera">peso {D._num(b["peso"], 1)}</span>{etq}</h4>
  <p class="glosa">{h(b["glosa"])}</p>
  {ev}
</article>""")
        out.append("</section>")
    return "".join(out)


NOTA_PRECISION = {
    "cabecera_municipal": "Ubicacion aproximada: cabecera municipal. No se pudo geocodificar "
                          "la direccion exacta, comun en zona rural.",
}


def bloque_mapa(c, geocache):
    """Mapa satelital de la seccion Ejecucion, o una nota si no hay ubicacion confiable.

    El fallback 'defecto' (centro de Colombia) de coords_contrato() nunca llega
    aqui: un mapa generico centrado en Bogota para un contrato de otro
    departamento es peor que no mostrar mapa. Sin evidencia no se publica.
    """
    if not D.ciudad_visible(c.get("ciudad")):
        return '<p class="mapa-nota sin">Municipio no definido en la fuente: no hay donde centrar un mapa.</p>', False
    coords = D.coords_contrato(c, geocache)
    if not coords:
        return '<p class="mapa-nota sin">Ubicacion no geocodificada todavia.</p>', False
    direccion = ", ".join(x for x in (D.titulo(c.get("dir_ejecucion")), D.ciudad_visible(c.get("ciudad"))) if x)
    nota = NOTA_PRECISION.get(coords["precision"], "")
    # Click-to-load (Tanda B, B6): las imagenes satelitales las sirve Esri
    # (server.arcgisonline.com) y eso NO se puede vendorizar. Pero pedirlas
    # solas al abrir la ficha le dice a Esri, sin que el lector lo sepa, que
    # coordenadas esta mirando -- y el publico de este sitio son periodistas.
    # El div lleva id="mapa-satelital" desde YA (test_privacy.py lo exige) y
    # los data-* con las coordenadas; mapa-satelital.js no llama a Leaflet
    # hasta que el lector pulsa el boton.
    html_mapa = (f'<div id="mapa-satelital" class="mapa-placeholder" data-lat="{h(coords["lat"])}" '
                f'data-lon="{h(coords["lon"])}" data-direccion="{h(direccion)}">'
                f'<p class="mapa-direccion">{h(direccion) or "Ubicacion sin direccion textual"}</p>'
                '<p class="nota">La imagen satelital la sirve Esri (arcgisonline.com): al cargarla, '
                'Esri recibe las coordenadas que esta viendo. No se pide sola.</p>'
                '<button type="button" class="btn btn-secondary">Ver imagen satelital</button></div>'
                + (f'<p class="mapa-nota">{h(nota)}</p>' if nota else ""))
    return html_mapa, True


def ficha_contrato(c, glos, hermanos, geocache):
    items, grupos = D.banderas_encendidas(c, glos)
    ciudad = c["_ciudad"]
    objeto = D.titulo(c.get("descripcion")) or "Objeto contractual no publicado"
    ent = D.titulo(c.get("entidad"))
    dep = D.titulo(c.get("departamento"))
    valor = c.get("valor_plausible")
    url = c.get("_url")

    verificar = (f'<a class="btn-verificar" href="{h(url)}" rel="noopener nofollow" '
                 f'target="_blank">Verificar en SECOP II &rarr;</a>' if url else
                 '<p class="btn-verificar sin">La fuente no publico enlace al proceso. '
                 'Sin verificacion en origen, tratelo como no confirmado.</p>')

    # dinero
    filas_plata = [dato("Valor del contrato", D.plata(valor),
                        f'<small>{D.plata(valor, exacto=True)}</small>')]
    if c.get("valor") and c["valor"] != valor:
        filas_plata.append(dato("Valor publicado por la entidad",
            f'<span class="alerta">{D.plata(c["valor"])}</span>',
            '<small>Cifra aritmeticamente imposible. Se trata como falla de publicacion; '
            'todas las sumas de este sitio usan el valor saneado.</small>'))
    for etq, k in (("Pagado", "valor_pagado"), ("Pendiente de ejecucion", "valor_pend_ejecucion"),
                   ("Anticipo", "valor_anticipo"), ("Precio base del estudio", "precio_base")):
        if c.get(k):
            filas_plata.append(dato(etq, D.plata(c[k])))

    recursos = [n for n, k in (("Regalias", "rec_regalias"), ("SGP", "rec_sgp"),
                               ("Recursos propios", "rec_propios_terr")) if c.get(k)]

    personas = [dato("Proveedor", h(D.titulo(c.get("proveedor"))) or "sin dato")]
    if c.get("ordenador"):
        personas.append(dato("Ordenador del gasto", h(D.titulo(c["ordenador"])),
                             "<small>Funcionario publico. Se publica el nombre, no el documento.</small>"))
    personas.append(dato("Supervisor", h(D.titulo(c.get("supervisor")))
                         or '<span class="alerta">no reportado</span>'))

    herm = ""
    if hermanos:
        li = "".join(f'<li><a href="{url_contrato(x)}">{h(D.titulo(x.get("descripcion")) or x["id_contrato"])}</a>'
                     f' <span>{D.plata(x.get("valor_plausible"))} &middot; {h(x.get("fecha_firma"))}</span></li>'
                     for x in hermanos[:8])
        herm = f"""<section class="caja"><h2>Otros contratos marcados del mismo proveedor</h2>
<p class="nota">Coincidencia de proveedor dentro de este municipio. Es contexto para
reportear, no una relacion probada entre los contratos.</p><ul class="lista-herm">{li}</ul></section>"""

    mapa_html, hay_mapa = bloque_mapa(c, geocache)

    cuerpo = f"""
<div class="aviso-fijo" role="note"><strong>Indicio, no acusacion.</strong>
  Este contrato esta marcado por patrones detectados en datos publicos. No afirma que
  alguien haya obrado de forma irregular. <a href="/metodologia/">Que significa esto</a></div>

{migas(("Plomada", "/"), (dep, f"/mapa/?dep={D.slug(c['departamento'])}"),
       (ciudad or "Municipio sin definir", url_municipio(c["departamento"], c["ciudad"]) if ciudad else None),
       ("Contrato", None))}

<article class="ficha">
  <header class="ficha-cab">
    <p class="tipo">{h(D.titulo(c.get("tipo_contrato")))} &middot; {h(D.titulo(c.get("modalidad")))}</p>
    <h1>{h(objeto)}</h1>
    <p class="idc"><code>{h(c["id_contrato"])}</code></p>
    {verificar}
  </header>

  <dl class="cab-grid">
    {dato("Entidad", h(ent), f'<small>NIT {h(c.get("nit_entidad"))} &middot; orden {h(D.titulo(c.get("orden")))}</small>')}
    {dato("Municipio", (f'<a href="{url_municipio(c["departamento"], c["ciudad"])}">{h(ciudad)}</a>'
                        if ciudad else '<span class="alerta">no definido en la fuente</span>')
          , f'<small>{h(dep)}</small>')}
    {dato("Valor", D.plata(valor))}
    {dato("Firma", h(c.get("fecha_firma")), f'<small>Periodo {h(c.get("periodo_gobierno"))}</small>')}
    {dato("Estado", h(D.titulo(c.get("estado"))))}
    {dato("Plazo", f'{D.entero(c.get("dias_originales"))} dias'
          + (f' <span class="alerta">+{D.entero(c["dias_adicionados"])} adicionados</span>'
             if c.get("dias_adicionados") else ""))}
  </dl>

  {barra_score(c)}

  <section class="caja principal">
    <h2>Senales de riesgo encendidas <span class="cuenta">{len(items)}</span></h2>
    <p class="nota">Agrupadas por tipo y ordenadas por peso. Cada una viene con el numero
       que la disparo: si el numero no le convence, el enlace a la fuente oficial esta arriba.</p>
    {bloque_banderas(grupos, len(items))}
  </section>

  <div class="dos-col">
    <section class="caja"><h2>Dinero</h2><dl class="dl">{"".join(filas_plata)}</dl>
      {'<p class="fuentes">Fuente de recursos: ' + ", ".join(recursos) + "</p>" if recursos else ""}
    </section>
    <section class="caja"><h2>Personas y competencia</h2><dl class="dl">{"".join(personas)}
      {dato("Ofertas recibidas", D.entero(c.get("n_oferentes_unicos")))}
      {dato("Invitados", D.entero(c.get("n_invitados")))}
      {dato("Ventana de publicacion", f'{D.entero(c.get("dias_ventana"))} dias',
            f'<small>Mediana de su modalidad: {D.entero(c.get("ev_ventana_mediana_modalidad"))} dias</small>')}
    </dl>
      <p class="nota">Los documentos de identidad de particulares no se publican.
         <a href="/metodologia/#privacidad">Por que</a></p>
    </section>
  </div>

  <section class="caja"><h2>Ejecucion</h2><dl class="dl">
    {dato("Direccion de ejecucion", h(D.titulo(c.get("dir_ejecucion"))))}
    {dato("Clasificacion UNSPSC", h(c.get("unspsc")))}
  </dl>
  {mapa_html}
  </section>

  {herm}
</article>
"""
    desc = (f"{len(items)} senales de riesgo en un contrato de {D.plata(valor)} de "
            f"{ent} en {ciudad or dep}. Indicio para revision, no acusacion.")
    head = LEAFLET_CSS if hay_mapa else ""
    js = (LEAFLET_JS + '<script src="/static/mapa-satelital.js"></script>') if hay_mapa else ""
    return pagina(objeto[:70], desc, cuerpo, url_contrato(c), head=head, js=js, clase="pg-ficha")


# ------------------------------------------------------------------ municipio
def pagina_municipio(m, contratos_mun, puesto, total_mun):
    ciudad = D.ciudad_visible(m["ciudad"])
    dep = D.titulo(m["departamento"])
    nombre = ciudad or f"Contratos sin municipio definido — {dep}"
    filas = "".join(
        f'<tr><td><a href="{url_contrato(c)}">{h(D.titulo(c.get("descripcion")) or c["id_contrato"])}</a>'
        f'<small>{h(D.titulo(c.get("entidad")))}</small></td>'
        f'<td class="num">{D.plata(c.get("valor_plausible"))}</td>'
        f'<td class="num">{h(c.get("anio"))}</td>'
        f'<td class="num">{c.get("n_banderas_fuertes") or 0}</td></tr>'
        for c in sorted(contratos_mun, key=lambda x: -(x.get("score") or 0)))

    conteos = [(k[2:].replace("_", " "), m[k]) for k in m
               if k.startswith("n_") and k not in ("n_contratos", "n_atipicos") and m[k]]
    chips = "".join(f'<li><b>{D.entero(v)}</b> {h(D.titulo(k))}</li>' for k, v in
                    sorted(conteos, key=lambda x: -x[1]))

    cuerpo = f"""
{migas(("Plomada", "/"), (dep, f"/mapa/?dep={D.slug(m['departamento'])}"), (nombre, None))}
<header class="cab-mun">
  <p class="tipo">{h(dep)}</p>
  <h1>{h(nombre)}</h1>
  <p class="puesto">Puesto {puesto} de {total_mun} municipios por tasa ajustada</p>
</header>
<dl class="cab-grid">
  {dato("Tasa ajustada", f'<b class="grande">{D.pct(m["tasa_ajustada"])}</b>',
        f'<small>Tasa cruda {D.pct(m["tasa_cruda"])} sobre {D.entero(m["n_contratos"])} contratos. '
        f'La ajustada corrige el azar de los municipios pequenos.</small>')}
  {dato("Contratos atipicos", f'{D.entero(m["n_atipicos"])} de {D.entero(m["n_contratos"])}')}
  {dato("Valor atipico", D.plata(m["valor_atipico"]),
        f'<small>{D.pct(m.get("share_valor_atipico") or 0)} de {D.plata(m["valor_total"])} contratados</small>')}
  {dato("Regalias en contratos atipicos", D.plata(m.get("regalias_atipicas")))}
</dl>
{'<section class="caja"><h2>Banderas mas frecuentes</h2><ul class="chips">' + chips + "</ul></section>" if chips else ""}
<section class="caja principal">
  <h2>Contratos marcados <span class="cuenta">{len(contratos_mun)}</span></h2>
  <p class="nota">Ordenados por puntaje. Cada uno abre su ficha con la evidencia y el
     enlace a SECOP II.</p>
  <div class="tabla-scroll"><table class="table"><thead><tr><th>Objeto</th><th class="num">Valor</th>
    <th class="num">Ano</th><th class="num">Senales fuertes</th></tr></thead>
    <tbody>{filas or '<tr><td colspan="4">Sin contratos en la muestra.</td></tr>'}</tbody></table></div>
  <p><a href="/buscar/?municipio={h(m['ciudad'])}">Ver en el buscador con filtros &rarr;</a></p>
</section>
"""
    desc = (f"{D.entero(m['n_atipicos'])} de {D.entero(m['n_contratos'])} contratos de obra "
            f"marcados en {nombre}. Tasa ajustada {D.pct(m['tasa_ajustada'])}.")
    return pagina(nombre, desc, cuerpo, url_municipio(m["departamento"], m["ciudad"]))


# ----------------------------------------------------------------------- 7.2 mapa
# El cruce ciudad (texto libre) -> DIVIPOLA lo resuelve otro frente del equipo.
# Aqui solo se consume: si aparece out/divipola_municipios.csv y geo/municipios.geojson,
# la capa municipal se pinta sola. Departamento si se resuelve por codigo oficial.
ALIAS_DEP = {
    "SANTAFE DE BOGOTA D.C": "BOGOTA D.C.",
    "ARCHIPIELAGO DE SAN ANDRES PROVIDENCIA Y SANTA CATALINA": "SAN ANDRES Y PROVIDENCIA",
}


def clave_dep(nombre):
    n = D.sin_tildes(nombre).replace(".", "").strip()
    n = D.sin_tildes(ALIAS_DEP.get(D.sin_tildes(nombre), n)).replace(".", "")
    return n.replace("BOGOTA DC", "BOGOTA").replace("SAN ANDRES Y PROVIDENCIA", "SAN ANDRES")


def pagina_mapa(deps, muns):
    por_clave = {clave_dep(d["departamento"]): d for d in deps}
    geo = json.loads((RAIZ / "geo" / "departamentos.geojson").read_text(encoding="utf-8"))
    sin_datos = []
    for f in geo["features"]:
        k = clave_dep(f["properties"].get("NOMBRE_DPT", ""))
        d = por_clave.pop(k, None)
        f["properties"] = {
            "nombre": D.titulo(d["departamento"]) if d else D.titulo(f["properties"]["NOMBRE_DPT"]),
            "raw": d["departamento"] if d else "",
            "cod": f["properties"].get("DPTO"),
            "slug": D.slug(d["departamento"]) if d else "",
            "ajustada": d["tasa_ajustada"] if d else None,
            "cruda": d["tasa_cruda"] if d else None,
            "n": d["n_contratos"] if d else 0,
            "a": d["n_atipicos"] if d else 0,
            "valor": d["valor_atipico"] if d else 0,
            "valor_fmt": D.plata(d["valor_atipico"]) if d else "sin dato",
        }
        if not d:
            sin_datos.append(f["properties"]["nombre"])
    (SITE / "datos").mkdir(parents=True, exist_ok=True)
    def redondear(o):   # 4 decimales ~ 11 m: el archivo baja a la mitad y el mapa no cambia
        if isinstance(o, float):
            return round(o, 4)
        if isinstance(o, list):
            return [redondear(x) for x in o]
        return o
    for f in geo["features"]:
        f["geometry"]["coordinates"] = redondear(f["geometry"]["coordinates"])
    (SITE / "datos" / "departamentos.geojson").write_text(
        json.dumps(geo, separators=(",", ":")), encoding="utf-8")

    huerfanos = sorted(por_clave)
    cross = (RAIZ / "out" / "divipola_municipios.csv").exists() and \
            (RAIZ / "geo" / "municipios.geojson").exists()

    orden = sorted(muns, key=lambda m: -m["tasa_ajustada"])
    filas = "".join(
        f'<tr data-dep="{h(D.slug(m["departamento"]))}"><td class="num">{i}</td>'
        f'<td><a href="{url_municipio(m["departamento"], m["ciudad"])}">'
        f'{h(D.ciudad_visible(m["ciudad"]) or "Sin municipio definido")}</a>'
        f'<small>{h(D.titulo(m["departamento"]))}</small></td>'
        f'<td class="num destacado">{D.pct(m["tasa_ajustada"])}</td>'
        f'<td class="num tenue">{D.pct(m["tasa_cruda"])}</td>'
        f'<td class="num">{D.entero(m["n_contratos"])}</td>'
        f'<td class="num">{D.plata(m["valor_atipico"])}</td></tr>'
        for i, m in enumerate(orden, 1))

    nota_mun = ("" if cross else """
<p class="nota aviso-cruce"><strong>Capa municipal pendiente.</strong> El cruce entre el
campo <code>ciudad</code> (texto libre) y los codigos DIVIPOLA lo esta resolviendo otro
frente del equipo. Este mapa no arma su propio pareo de nombres a proposito: pintar un
municipio equivocado es peor que no pintarlo. Mientras llega
<code>out/divipola_municipios.csv</code>, los 721 municipios estan en la tabla de abajo,
ordenados por la misma metrica.</p>""")

    aviso_faltantes = (f'<p class="nota">Sin datos en el mapa: {", ".join(sin_datos)}.</p>'
                       if sin_datos else "")
    aviso_huerfanos = (f'<p class="nota alerta">Departamentos en los datos que no cruzaron con '
                       f'una frontera oficial: {", ".join(huerfanos)}.</p>' if huerfanos else "")

    cuerpo = f"""
<header class="cab">
  <h1>Mapa de senales de riesgo</h1>
  <p class="bajada">Coropletico por <strong>tasa ajustada</strong> de contratos de obra
     marcados. Nunca por tasa cruda: un municipio con 4 contratos y 2 marcados da 50% y
     encabezaria la lista por puro azar. <a href="/metodologia/#tasa">Como se corrige</a></p>
</header>
<div class="mapa-wrap">
  <div id="mapa" role="application" aria-label="Mapa coropletico de Colombia"></div>
  <aside id="panel" class="panel"><p class="vacio">Elija un departamento en el mapa.</p></aside>
</div>
{aviso_faltantes}{aviso_huerfanos}
<section class="caja principal">
  <h2>Municipios <span class="cuenta">{len(muns)}</span></h2>
  {nota_mun}
  <p class="nota">Se muestran las dos tasas juntas: la ajustada, que es la que ordena, y
     la cruda, para que la correccion sea visible.</p>
  <input id="filtro-mun" type="search" placeholder="Filtrar municipio o departamento"
         aria-label="Filtrar municipios">
  <div class="tabla-scroll"><table class="table" id="tabla-mun"><thead><tr><th class="num">#</th><th>Municipio</th>
    <th class="num">Tasa ajustada</th><th class="num">Tasa cruda</th>
    <th class="num">Contratos</th><th class="num">Valor atipico</th></tr></thead>
    <tbody>{filas}</tbody></table></div>
</section>
"""
    head = LEAFLET_CSS
    js = LEAFLET_JS + '<script src="/static/mapa.js"></script>'
    return pagina("Mapa", "Mapa de Colombia por tasa ajustada de contratos de obra publica "
                  "con senales de riesgo, por departamento y municipio.", cuerpo, "/mapa/",
                  head=head, js=js, clase="pg-mapa")


# --------------------------------------------------------------------- 7.3 buscar
def pagina_buscar(glos, facetas):
    def opts(nombre, valores, etiqueta_fn=D.titulo):
        o = "".join(f'<option value="{h(v)}">{h(etiqueta_fn(v))}</option>' for v in valores)
        return f'<select id="f-{nombre}" data-campo="{nombre}"><option value="">Todos</option>{o}</select>'

    banderas_opt = "".join(
        f'<option value="{h(b)}">{h(D.titulo(b.removeprefix("f_").replace("_", " ")))}'
        f' ({h(glos[b]["grupo"])})</option>'
        for b in sorted(glos, key=lambda x: (glos[x]["grupo"], -glos[x]["peso"])))

    cuerpo = f"""
<header class="cab">
  <h1>Buscador de contratos marcados</h1>
  <p class="bajada">Filtre, ordene y llevese los datos. Cada busqueda tiene su propia URL:
     el enlace de la barra de direcciones ya lleva los filtros puestos.</p>
</header>
<form class="filtros" id="filtros" role="search">
  <div><label for="f-q">Texto</label>
    <input id="f-q" data-campo="q" type="search" placeholder="Objeto, entidad o proveedor"></div>
  <div><label for="f-departamento">Departamento</label>{opts("departamento", facetas["departamento"])}</div>
  <div><label for="f-municipio">Municipio</label>{opts("municipio", facetas["municipio"])}</div>
  <div><label for="f-entidad">Entidad</label>{opts("entidad", facetas["entidad"])}</div>
  <div><label for="f-anio">Ano</label>{opts("anio", facetas["anio"], str)}</div>
  <div><label for="f-periodo">Periodo de gobierno</label>{opts("periodo", facetas["periodo"], str)}</div>
  <div><label for="f-tipo">Tipo</label>{opts("tipo", facetas["tipo"])}</div>
  <div><label for="f-modalidad">Modalidad</label>{opts("modalidad", facetas["modalidad"])}</div>
  <div><label for="f-bandera">Bandera</label>
    <select id="f-bandera" data-campo="bandera"><option value="">Cualquiera</option>{banderas_opt}</select></div>
  <div><label for="f-vmin">Valor minimo (COP)</label>
    <input id="f-vmin" data-campo="vmin" type="number" min="0" step="1000000" placeholder="0"></div>
  <div><label for="f-vmax">Valor maximo (COP)</label>
    <input id="f-vmax" data-campo="vmax" type="number" min="0" step="1000000" placeholder="sin tope"></div>
  <div class="acciones">
    <button type="button" id="limpiar">Limpiar</button>
    <button type="button" id="exportar">Exportar CSV</button>
  </div>
</form>
<p id="resumen" class="resumen" aria-live="polite">Cargando…</p>
<div class="tabla-scroll"><table class="table" id="resultados">
  <thead><tr>
    <th data-orden="descripcion">Objeto</th>
    <th data-orden="entidad">Entidad</th>
    <th data-orden="municipio">Municipio</th>
    <th class="num" data-orden="anio">Ano</th>
    <th class="num" data-orden="valor">Valor</th>
    <th class="num" data-orden="fuertes">Senales</th>
    <th class="num" data-orden="score">Puntaje</th>
  </tr></thead><tbody></tbody>
</table></div>
<p><button type="button" id="mas" hidden>Ver mas</button></p>
<p class="nota">El CSV que descarga es el mismo que ve, ya saneado: no incluye documentos
   de particulares ni numeros de cuenta. <a href="/metodologia/#privacidad">Por que</a></p>
"""
    return pagina("Buscador", "Buscador de contratos de obra publica con senales de riesgo: "
                  "filtros por departamento, municipio, entidad, ano, modalidad y bandera.",
                  cuerpo, "/buscar/", js='<script type="module" src="/static/buscar.js"></script>',
                  clase="pg-buscar")


# ---------------------------------------------------------------- 7.4 metodologia
def pagina_metodologia(glos, cifras, umbral):
    por_grupo = defaultdict(list)
    for b in glos.values():
        por_grupo[b["grupo"]].append(b)
    bloques = []
    for g in D.ORDEN_GRUPOS + [x for x in sorted(por_grupo) if x not in D.ORDEN_GRUPOS]:
        if g not in por_grupo:
            continue
        filas = "".join(
            f'<tr><td><b>{h(D.titulo(b["bandera"].removeprefix("f_").replace("_", " ")))}</b>'
            f'<code>{h(b["bandera"])}</code></td>'
            f'<td class="num">{D._num(b["peso"], 1)}</td><td>{h(b["glosa"])}</td></tr>'
            for b in sorted(por_grupo[g], key=lambda x: -x["peso"]))
        bloques.append(f'<h3>{h(g)}</h3><div class="tabla-scroll"><table class="table banderas"><thead><tr>'
                       f'<th>Bandera</th><th class="num">Peso</th>'
                       f'<th>Que pregunta y en que se apoya</th></tr></thead><tbody>{filas}</tbody></table></div>')

    fp = "".join(f"""<article class="caso"><h3>{h(t)}</h3>
      <p><span class="etq">Que pasaba</span> {p}</p>
      <p><span class="etq">Que se hizo</span> {q}</p></article>""" for t, p, q in C.FALSOS_POSITIVOS)
    lim = "".join(f"<li><strong>{h(t)}</strong> {p}</li>" for t, p in C.LIMITACIONES)
    cob = "".join(f'<tr><td><code>{h(k)}</code></td><td class="num">{v}</td></tr>'
                  for k, v in [("dir_ejecucion", "100%"), ("doc_proveedor", "87,4%"),
                               ("doc_ordenador", "64,5%"), ("doc_supervisor", "54,3%"),
                               ("doc_replegal", "30,9%"), ("cuenta bancaria", "23,7%")])

    cuerpo = f"""
<header class="cab">
  <h1>Metodologia</h1>
  <p class="bajada">Que mide Plomada, como lo mide, y sobre todo que <em>no</em> puede
     afirmar. Esta pagina es parte del producto, no un anexo.</p>
</header>
{C.INTRO_METODOLOGIA}

<section class="caja"><h2>El universo analizado</h2>
<dl class="cab-grid">
  {dato("Contratos en SECOP II", "5.975.627", "<small>de los cuales 5.123.891 son prestacion de servicios</small>")}
  {dato("Universo de obra publica", "<b class='grande'>77.864</b>", "<small>Obra 52.355 &middot; Interventoria 13.074 &middot; Consultoria 11.482 &middot; APP 715 &middot; Concesion 238</small>")}
  {dato("Valor total", "$209 billones")}
  {dato("Contratos atipicos", "11.121 <span class='tenue'>(14,3%)</span>", "<small>$11,7 billones</small>")}
</dl>
<p class="nota">En Colombia un billon son 10<sup>12</sup> pesos. Todo el dinero de este
   sitio se suma con <code>valor_plausible</code>, la version saneada del valor
   publicado. <a href="#falsos">Por que</a></p>
</section>

<section class="caja" id="banderas"><h2>Las {len(glos)} banderas</h2>
<p class="nota">Nombres, pesos y glosas salen de <code>banderas_glosario.csv</code>.
   No estan escritas en el codigo del sitio: si el pipeline agrega una bandera, aparece
   aqui sola.</p>
{"".join(bloques)}
</section>

<section class="caja" id="puntaje"><h2>Como se calcula el puntaje</h2>
{C.PUNTAJE}
<p class="nota">En el corte vigente, el contrato marcado con menos senales acumula
   {D._num(umbral, 1)} puntos crudos y el conjunto de atipicos promedia
   {D._num(cifras["score_medio"], 2)} de puntaje.</p>
</section>

<section class="caja" id="tasa"><h2>Por que la tasa ajustada y no el porcentaje</h2>
<p>Ordenar municipios por porcentaje de contratos marcados premia a los municipios
   pequenos. Con 4 contratos, dos marcados dan 50%: el mismo numero que un municipio con
   200 contratos y 100 marcados, cuando la evidencia detras es incomparable.</p>
<p>La <strong>tasa ajustada</strong> contrae cada municipio hacia la tasa nacional en
   proporcion a lo poco que se sabe de el, con un prior Beta estimado sobre el conjunto
   de municipios. Un municipio con muchos contratos casi no se mueve; uno con cuatro se
   mueve mucho. Los parametros <code>alpha</code> y <code>beta</code> viajan en el CSV de
   rankings para que el calculo se pueda reproducir.</p>
<p>El sitio muestra siempre las dos tasas, la cruda al lado de la ajustada. Esconder la
   correccion no genera confianza; ensenarla si.</p>
</section>

<section class="caja" id="falsos"><h2>Falsos positivos conocidos</h2>
<p class="nota">Casos reales en que una bandera se encendia sin que hubiera nada que
   revisar. Se listan porque un lector tiene derecho a saber donde falla la herramienta.</p>
{fp}
</section>

<section class="caja" id="limitaciones"><h2>Limitaciones</h2>
<ul class="lista-lim">{lim}</ul>
<h3>Cobertura por campo</h3>
<p class="nota">El analisis de red solo puede calcularse sobre los contratos que traen el
   identificador. Es un piso, no un censo.</p>
<div class="tabla-scroll"><table class="table"><thead><tr><th>Campo</th><th class="num">Cobertura</th></tr></thead>
  <tbody>{cob}</tbody></table></div>
</section>

<section class="caja" id="privacidad"><h2>Que no se publica</h2>
{C.PRIVACIDAD}
</section>

<section class="caja" id="fuentes"><h2>Datos crudos y codigo</h2>
{C.FUENTES}
</section>
"""
    return pagina("Metodologia", "Las 22 banderas con su peso y su glosa, como se calcula "
                  "el puntaje, los falsos positivos conocidos y los limites de cobertura.",
                  cuerpo, "/metodologia/", clase="pg-texto")


# --------------------------------------------------------------------- portada
def portada(muns, cifras, top_contratos):
    top = sorted(muns, key=lambda m: -m["tasa_ajustada"])[:10]
    filas = "".join(
        f'<tr><td class="num">{i}</td><td><a href="{url_municipio(m["departamento"], m["ciudad"])}">'
        f'{h(D.ciudad_visible(m["ciudad"]) or "Sin municipio definido")}</a>'
        f'<small>{h(D.titulo(m["departamento"]))}</small></td>'
        f'<td class="num destacado">{D.pct(m["tasa_ajustada"])}</td>'
        f'<td class="num tenue">{D.pct(m["tasa_cruda"])}</td>'
        f'<td class="num">{D.entero(m["n_contratos"])}</td></tr>'
        for i, m in enumerate(top, 1))
    tarjetas = "".join(
        f'<a class="card elev-sm" href="{url_contrato(c)}">'
        f'<span class="card-kicker">{c["n_banderas_fuertes"]} senales fuertes</span>'
        f'<b class="card-title">{h((D.titulo(c.get("descripcion")) or "Objeto no publicado")[:80])}</b>'
        f'<span class="card-meta">{h(D.titulo(c.get("entidad")))[:60]} &middot; '
        f'{h(D.ciudad_visible(c.get("ciudad")) or D.titulo(c.get("departamento")))} &middot; '
        f'{D.plata(c.get("valor_plausible"))}</span></a>' for c in top_contratos)

    cuerpo = f"""
<header class="hero">
  <p class="kicker">Obra publica &middot; SECOP II &middot; datos abiertos</p>
  <h1>La plomada revela lo que esta torcido</h1>
  <p class="lema">Esta sigue <strong>personas</strong>, no empresas, en la contratacion de
     obra publica del Estado colombiano.</p>
  <p class="bajada">Una empresa se disuelve y manana aparece otra con otro NIT. Una cedula no.
     Por eso Plomada mira las cuatro personas que firman cada contrato: quien autorizo el
     gasto, quien debia supervisar, quien representa a la empresa y quien autorizo el pago.</p>
  <p class="cta"><a class="btn btn-primary" href="/buscar/">Buscar un contrato</a>
     <a class="btn btn-secondary" href="/mapa/">Ver el mapa</a></p>
</header>

{isla("cifra-lider",
      '<p class="nota">Ver el desglose completo de indicios en el '
      '<a href="/tablero/">tablero</a>.</p>')}

<dl class="cab-grid cifras">
  {dato("Universo de obra publica", "<b class='grande'>77.864</b>", "<small>contratos, $209 billones</small>")}
  {dato("Contratos atipicos", "<b class='grande'>11.121</b>", "<small>14,3% &middot; $11,7 billones</small>")}
  {dato("Municipios en el ranking", D.entero(cifras["n_municipios"]))}
  {dato("Administraciones", D.entero(cifras["n_admin"]), "<small>entidad x periodo de gobierno</small>")}
</dl>
<section class="caja principal">
  <h2>Municipios con mayor tasa ajustada</h2>
  <p class="nota">Ordenado por tasa ajustada, nunca por la cruda. Las dos se muestran
     juntas. <a href="/metodologia/#tasa">Por que</a></p>
  <div class="tabla-scroll"><table class="table"><thead><tr><th class="num">#</th><th>Municipio</th>
    <th class="num">Tasa ajustada</th><th class="num">Tasa cruda</th>
    <th class="num">Contratos</th></tr></thead><tbody>{filas}</tbody></table></div>
  <p><a href="/mapa/">Ver los {D.entero(cifras['n_municipios'])} municipios en el mapa &rarr;</a></p>
</section>
<section class="caja"><h2>Contratos con mas senales fuertes</h2>
  <div class="tarjetas">{tarjetas}</div>
</section>

<div class="cierre">
  <div class="cierre-inner">
    <h2>Un indicio no es una acusacion.</h2>
    <p>Todo lo que aparece en Plomada es un indicio calculado sobre datos publicos del
       SECOP II para priorizar revision periodistica y control social. No afirma que
       ninguna persona o entidad haya obrado de forma irregular.
       <a href="/metodologia/">Como se calcula</a> &middot; <a href="/datos/">Descargar los datos</a></p>
  </div>
</div>
"""
    return pagina(LEMA, "Plomada detecta indicios de irregularidad en la contratacion de obra "
                  "publica en Colombia siguiendo a las personas que firman, no a las empresas. "
                  "Datos publicos del SECOP II.", cuerpo, "/", clase="pg-portada",
                  js=ISLAS_JS)


def pagina_tablero():
    """El tablero (B2): vision agregada sobre datos/*.json (Tanda A los deja
    en site/datos/ si existe out_web/; si no, tablero.js degrada avisando en
    vez de romper -- igual que el resto del sitio cuando falta un dato).

    Los cinco graficos viven en static/graficos/ (B3): un modulo = un
    grafico = una unidad de datos clara, cada uno importando formato.js
    (B4) en vez de reimplementar plata/pct/entero/titulo. tablero.js es
    el orquestador de pagina: hace fetch, reparte los datos y llama a
    cada modulo.
    """
    cuerpo = f"""
{aviso_fijo("Cada cifra de este tablero mide cuanta plata publica paso por "
            "contratos con indicios verificables. Ninguna mide cuanta plata se "
            "robaron: eso requiere una investigacion judicial que este proyecto "
            "no hace ni reemplaza.")}

<header class="cab">
  <h1>Tablero</h1>
  <p class="bajada">Vision agregada de los indicios: cuanta plata publica paso por
     contratos marcados, por indicio, por territorio y por red de proveedores.</p>
</header>

<p class="nota vacio" id="t-error" hidden>No se pudieron cargar los datos del tablero.
  Corra <code>pipeline/export_web.py</code> y <code>plomada/build.py</code> otra vez.</p>

<section class="caja hero" id="t-hero">
  <p class="tipo">Obra publica adjudicada sin competencia real (un solo oferente)</p>
  <p class="valor grande" id="t-hero-valor">—</p>
  <p class="nota" id="t-hero-nota">—</p>
</section>
<dl class="cab-grid cifras" id="t-tiles"></dl>

<section class="caja principal">
  <h2>Donde esta la plata en riesgo</h2>
  <p class="nota">Un contrato puede presentar varios indicios a la vez, asi que
     <b>las barras no se suman entre si</b>: cada una se compara contra el total
     del universo, no contra las otras.</p>
  <div id="t-indicios"></div>
  <details class="tbl"><summary>Ver tabla</summary><div id="t-tbl-indicios"></div></details>
</section>

<section class="caja">
  <h2>Territorio</h2>
  <form class="filtros" id="t-filtros-territorio">
    <div><label for="t-f-dep">Departamento</label>
      <select id="t-f-dep"><option value="">Todos</option></select></div>
    <div><label for="t-f-min">Minimo de contratos</label>
      <select id="t-f-min"><option value="20">20</option><option value="40">40</option>
        <option value="80">80</option></select></div>
  </form>
</section>

<section class="caja">
  <h2>Municipios: por que la tasa cruda enganha</h2>
  <p class="nota">Un municipio con 4 contratos y 2 marcados da 50% y encabeza cualquier
     lista sin significar nada. La tasa ajustada corrige eso con encogimiento bayesiano
     empirico. Se muestran <b>las dos</b>, siempre.</p>
  <div id="t-leyenda-municipios"></div>
  <div id="t-municipios"></div>
  <details class="tbl"><summary>Ver tabla</summary><div id="t-tbl-municipios"></div></details>
</section>

<section class="caja">
  <h2>Departamentos: tamano del contrato vs. falta de competencia</h2>
  <p class="nota">Eje horizontal en escala logaritmica porque el gasto va de miles de
     millones a cientos de billones. El tamano del punto es el numero de contratos.</p>
  <div id="t-departamentos"></div>
  <details class="tbl"><summary>Ver tabla</summary><div id="t-tbl-departamentos"></div></details>
</section>

<section class="caja">
  <h2>Red de proveedores</h2>
  <p class="nota">Empresas unidas por una llave que deberia ser unica: la misma cuenta
     bancaria, el mismo representante legal o el mismo domicilio. Cuando un mismo grupo
     concentra la obra <b>y</b> su interventoria, el que vigila y el que construye son
     la misma red.</p>
  <form class="filtros" id="t-filtros-red">
    <div><label for="t-f-cl">Grupo</label><select id="t-f-cl"></select></div>
  </form>
  <div id="t-leyenda-red"></div>
  <div id="t-red"></div>
  <p class="nota" id="t-red-nota"></p>
  <details class="tbl"><summary>Ver tabla</summary><div id="t-tbl-red"></div></details>
</section>

<section class="caja">
  <h2>Limitaciones</h2>
  <ul class="lista-lim" id="t-limitaciones"></ul>
</section>
"""
    return pagina("Tablero", "Vision agregada de los indicios de riesgo en la contratacion "
                  "de obra publica: por indicio, por territorio y por red de proveedores.",
                  cuerpo, "/tablero/", js='<script type="module" src="/static/tablero.js"></script>',
                  clase="pg-tablero")


def pagina_datos(archivos):
    li = "".join(f'<li><a href="/datos/{h(n)}" download><code>{h(n)}</code></a> '
                 f'<span>{h(desc)}</span> <small>{k:,.0f} KB</small></li>'.replace(",", ".")
                 for n, desc, k in archivos)
    cuerpo = f"""
<header class="cab"><h1>Datos</h1>
<p class="bajada">Si el proyecto es publico, la gente tiene que poder llevarse los datos.
   Estos archivos son los que alimentan el sitio, ya saneados de identificadores
   personales. <a href="/metodologia/#privacidad">Que se quito y por que</a></p></header>
<section class="caja"><ul class="descargas">{li}</ul>
<p class="nota">Fuente primaria: SECOP II, Colombia Compra Eficiente. Fronteras: DANE.
   Estos CSV son derivados; para reproducir el analisis desde cero, empiece por la fuente.</p>
</section>"""
    return pagina("Datos", "Descarga de los datos derivados de Plomada en CSV y GeoJSON.",
                  cuerpo, "/datos/", clase="pg-texto")


# -------------------------------------------------------------------------- main
def copiar_datos_tablero():
    """Copia los JSON de pipeline/export_web.py (out_web/) a site/datos/.

    export_web.py YA NO escribe dentro de site/ directamente (Tanda A, A4):
    build.py sigue siendo la UNICA pluma que toca site/, asi test_privacy.py
    barre un solo artefacto completo, no dos escritores por separado. Si
    out_web/ no existe todavia (no se corrio export_web.py o no hay
    warehouse), se sigue de largo: el resto del sitio se genera igual, nada
    mas el tablero queda sin esos datos.
    """
    if not OUT_WEB.exists():
        print(f"aviso: no existe {OUT_WEB}, el tablero queda sin datos de export_web.py "
              "(corra pipeline/export_web.py si hace falta)", file=sys.stderr)
        return
    destino = SITE / "datos"
    destino.mkdir(parents=True, exist_ok=True)
    for f in OUT_WEB.glob("*.json"):
        shutil.copy2(f, destino / f.name)
    print(f"datos del tablero copiados de {OUT_WEB} a site/datos/", file=sys.stderr)


def main():
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    shutil.copytree(RAIZ / "static", SITE / "static")
    copiar_datos_tablero()

    glos = D.glosario()
    geocache = D.cargar_geocache()
    contratos = list(D.contratos())
    muns, deps, admins = D.municipios(), D.departamentos(), D.administraciones()
    if not contratos:
        sys.exit(f"{D.OUT}/ vacio. Corra: python3 gen_synthetic.py (o revise $PLOMADA_OUT)")

    por_mun = defaultdict(list)
    for c in contratos:
        por_mun[(c["departamento"], c["ciudad"])].append(c)
    por_prov_mun = defaultdict(list)
    for c in contratos:
        por_prov_mun[(c["departamento"], c["ciudad"], c.get("proveedor"))].append(c)

    # 7.1
    for c in contratos:
        hermanos = [x for x in por_prov_mun[(c["departamento"], c["ciudad"], c.get("proveedor"))]
                    if x["id_contrato"] != c["id_contrato"]]
        escribir(url_contrato(c).strip("/") + "/index.html", ficha_contrato(c, glos, hermanos, geocache))

    # municipios
    orden_mun = sorted(muns, key=lambda m: -m["tasa_ajustada"])
    puesto = {(m["departamento"], m["ciudad"]): i for i, m in enumerate(orden_mun, 1)}
    for m in muns:
        k = (m["departamento"], m["ciudad"])
        escribir(url_municipio(*k).strip("/") + "/index.html",
                 pagina_municipio(m, por_mun.get(k, []), puesto[k], len(muns)))

    # tablero (B2)
    escribir("tablero/index.html", pagina_tablero())

    # 7.2
    escribir("mapa/index.html", pagina_mapa(deps, muns))

    # 7.3 — indice slim, ya saneado
    indice = []
    for c in contratos:
        p = D.publicar(c)
        indice.append({
            "u": url_contrato(c), "d": D.titulo(p.get("descripcion")) or "Objeto no publicado",
            "e": D.titulo(p.get("entidad")), "dep": p.get("departamento"), "mun": p.get("ciudad"),
            "munv": p.get("_ciudad") or "Sin municipio definido", "pv": D.titulo(p.get("proveedor")),
            "a": p.get("anio"), "per": p.get("periodo_gobierno"), "t": p.get("tipo_contrato"),
            "m": p.get("modalidad"), "v": p.get("valor_plausible") or 0,
            "s": p.get("score") or 0, "nf": p.get("n_banderas_fuertes") or 0,
            "f": [k for k, v in p.items() if k.startswith("f_") and v],
            "id": p.get("id_contrato"), "url": p.get("_url") or "",
        })
    escribir_json("datos/contratos.json", indice)
    escribir_json("datos/banderas.json", {k: {kk: vv for kk, vv in v.items()} for k, v in glos.items()})
    facetas = {
        "departamento": sorted({c["departamento"] for c in contratos}),
        "municipio": sorted({c["ciudad"] for c in contratos}),
        "entidad": sorted({c["entidad"] for c in contratos}),
        "anio": sorted({c["anio"] for c in contratos if c.get("anio")}),
        "periodo": sorted({c["periodo_gobierno"] for c in contratos if c.get("periodo_gobierno")}),
        "tipo": sorted({c["tipo_contrato"] for c in contratos}),
        "modalidad": sorted({c["modalidad"] for c in contratos}),
    }
    escribir("buscar/index.html", pagina_buscar(glos, facetas))

    # 7.4
    umbral = min((c.get("puntos_crudos") or 0) for c in contratos)
    cifras = {"n_municipios": len(muns), "n_admin": len(admins),
              "score_medio": sum(c.get("score") or 0 for c in contratos) / len(contratos)}
    escribir("metodologia/index.html", pagina_metodologia(glos, cifras, umbral))

    # portada
    top_contratos = sorted(contratos, key=lambda c: (-(c.get("n_banderas_fuertes") or 0),
                                                     -(c.get("score") or 0)))[:6]
    escribir("index.html", portada(muns, cifras, top_contratos))

    # descargas saneadas
    archivos = exportar_csvs(contratos, muns, deps, admins, glos)
    escribir("datos/index.html", pagina_datos(archivos))

    # sitemap + robots
    urls = ["/", "/tablero/", "/mapa/", "/buscar/", "/metodologia/", "/datos/"] + \
           [url_contrato(c) for c in contratos] + \
           [url_municipio(m["departamento"], m["ciudad"]) for m in muns]
    escribir("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
             + "".join(f"<url><loc>{h(u)}</loc></url>" for u in urls) + "</urlset>")
    escribir("robots.txt", "User-agent: *\nAllow: /\nSitemap: /sitemap.xml\n")

    print(f"site/: {len(contratos)} fichas, {len(muns)} municipios, {len(glos)} banderas, "
          f"{len(urls)} URLs.")

    # La prueba de privacidad tumba el build. Si algo prohibido llego a un archivo,
    # no queda nada que alguien pueda publicar por error.
    import test_privacy
    try:
        test_privacy.main()
    except SystemExit:
        shutil.rmtree(SITE)
        sys.exit("  site/ borrado: no se publica hasta que la prueba pase.")


def escribir_json(ruta, obj):
    p = SITE / ruta
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def exportar_csvs(contratos, muns, deps, admins, glos):
    salida = []
    tablas = [("contratos_atipicos.csv", [D.publicar(c) for c in contratos],
               "Contratos marcados, saneado de documentos y cuentas"),
              ("ranking_municipios.csv", muns, "721 municipios con tasa cruda y ajustada"),
              ("ranking_departamentos.csv", deps, "34 departamentos, capa base del mapa"),
              ("ranking_administraciones.csv", admins, "Entidad x periodo de gobierno"),
              ("banderas_glosario.csv", list(glos.values()), "Las banderas con su peso y glosa")]
    for nombre, filas, desc in tablas:
        if not filas:
            continue
        cols = [k for k in filas[0] if not k.startswith("_")]
        ruta = SITE / "datos" / nombre
        with open(ruta, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(filas)
        salida.append((nombre, desc, ruta.stat().st_size / 1024))
    g = SITE / "datos" / "departamentos.geojson"
    if g.exists():
        salida.append(("departamentos.geojson", "Fronteras departamentales con la tasa ajustada",
                       g.stat().st_size / 1024))
    return salida


if __name__ == "__main__":
    main()
