/* Orquestador de /tablero/ (Tanda B, B2). Hace fetch de datos/*.json (los
 * deja ahi copiar_datos_tablero() de build.py, leyendo out_web/ -- Tanda A),
 * reparte los datos y llama a cada modulo de graficos/ (B3). No dibuja nada
 * el mismo: cada grafico es su propia unidad con entrada de datos clara,
 * este archivo solo es el pegamento de la pagina (en fase 2, el componente
 * padre que le pasa props a cada hijo).
 *
 * Si un JSON no esta (no se corrio pipeline/export_web.py, o no hay
 * warehouse) el tablero degrada avisando, nunca revienta: el resto del
 * sitio ya sigue ese patron (D.OUT en data.py, copiar_datos_tablero() en
 * build.py).
 */
import { plata, pct, entero } from "./formato.js";
import * as Indicios from "./graficos/indicios.js";
import * as Municipios from "./graficos/municipios.js";
import * as Departamentos from "./graficos/departamentos.js";
import * as Red from "./graficos/red.js";

const ARCHIVOS = ["titulares", "indicios", "municipios", "departamentos", "tipo_obra",
                  "fuentes", "autosupervision", "red", "meta"];

function porId(id) { return document.getElementById(id); }

function dato(etiqueta, valor, nota) {
  const div = document.createElement("div");
  div.className = "dato";
  const dt = document.createElement("dt");
  dt.textContent = etiqueta;
  const dd = document.createElement("dd");
  dd.textContent = valor;
  if (nota) {
    const small = document.createElement("small");
    small.textContent = nota;
    dd.append(document.createElement("br"), small);
  }
  div.append(dt, dd);
  return div;
}

function T(D, concepto) {
  return D.titulares.find((t) => t.concepto === concepto) || {};
}

async function cargar() {
  try {
    const res = await Promise.all(ARCHIVOS.map((n) => fetch(`/datos/${n}.json`).then((r) => {
      if (!r.ok) throw new Error(`${n}.json: HTTP ${r.status}`);
      return r.json();
    })));
    const D = {};
    ARCHIVOS.forEach((n, i) => { D[n] = res[i]; });
    iniciar(D);
  } catch (e) {
    console.error(e);
    const err = porId("t-error");
    if (err) err.hidden = false;
  }
}

function iniciar(D) {
  const universo = T(D, "Obra publica analizada");
  const sinComp = T(D, "Adjudicado sin competencia real");
  porId("t-hero-valor").textContent = plata(sinComp.valor);
  porId("t-hero-nota").textContent =
    `${pct(sinComp.valor / universo.valor)} de los ${plata(universo.valor)} de obra publica ` +
    `analizada · ${entero(sinComp.n_contratos)} contratos`;

  const atip = T(D, "Clasificado atipico (indicio fuerte o 6+ puntos)");
  const conRed = T(D, "Con indicio fuerte de red");
  const ambas = T(D, "Con indicios de tramite Y de red");
  const tiles = [
    ["Obra publica analizada", plata(universo.valor), `${entero(universo.n_contratos)} contratos`],
    ["Clasificados atipicos", entero(atip.n_contratos),
      `${plata(atip.valor)} · umbral: indicio fuerte o 6 puntos`],
    ["Con indicio fuerte de red", entero(conRed.n_contratos), plata(conRed.valor)],
    ["Atipicos por tramite y por red", entero(ambas.n_contratos), "los primeros de la fila"],
    ["Grupos economicos detectados", entero(D.meta.n_clusters), "empresas unidas por una llave unica"],
  ];
  porId("t-tiles").replaceChildren(...tiles.map(([l, v, n]) => dato(l, v, n)));

  porId("t-limitaciones").replaceChildren(...D.meta.limitaciones.map((txt) => {
    const li = document.createElement("li");
    li.textContent = txt;
    return li;
  }));

  Indicios.dibujar(porId("t-indicios"), porId("t-tbl-indicios"), D.indicios, universo.valor);

  fillFiltrosTerritorio(D);
  dibujarTerritorio(D);

  fillFiltrosRed(D);
  dibujarRed(D);
}

/* ---------- territorio: municipios + departamentos comparten filtro ---------- */
function fillFiltrosTerritorio(D) {
  const deps = [...new Set(D.municipios.map((m) => m.departamento))].filter(Boolean).sort();
  const sel = porId("t-f-dep");
  deps.forEach((d) => sel.add(new Option(d, d)));
  sel.addEventListener("change", () => dibujarTerritorio(D));
  porId("t-f-min").addEventListener("change", () => dibujarTerritorio(D));
}

function sliceTerritorio(D) {
  const dep = porId("t-f-dep").value;
  const min = +porId("t-f-min").value;
  return {
    mun: D.municipios.filter((m) => (!dep || m.departamento === dep) && m.n_contratos >= min),
    dep: D.departamentos.filter((d) => !dep || d.departamento === dep),
  };
}

function dibujarTerritorio(D) {
  const s = sliceTerritorio(D);
  Municipios.dibujar(porId("t-municipios"), porId("t-tbl-municipios"), porId("t-leyenda-municipios"), s.mun);
  Departamentos.dibujar(porId("t-departamentos"), porId("t-tbl-departamentos"), s.dep);
}

/* ---------- red de proveedores ---------- */
function fillFiltrosRed(D) {
  const sel = porId("t-f-cl");
  D.red.forEach((c, i) => {
    const t = `${c.nodos.length} empresas · ${plata(c.valor)}` +
      (c.vigila_y_construye ? " · vigila y construye" : "");
    sel.add(new Option(t, i));
  });
  sel.addEventListener("change", () => dibujarRed(D));
}

function dibujarRed(D) {
  if (!D.red.length) return;
  const cluster = D.red[+porId("t-f-cl").value || 0];
  Red.dibujar(porId("t-red"), porId("t-tbl-red"), porId("t-leyenda-red"), porId("t-red-nota"), cluster);
}

cargar();
