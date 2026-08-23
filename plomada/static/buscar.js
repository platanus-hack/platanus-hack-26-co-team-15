/* Buscador cliente sobre /datos/contratos.json. El estado vive en la query
   string: la URL de la barra ya es el enlace compartible con los filtros.

   Modulo ES (no IIFE clasico): plata() vive una sola vez, en formato.js, y
   este archivo la importa en vez de tener su propia copia divergente. Por
   eso build.py debe cargar este script con type="module". */
import { plata } from './formato.js';

(function () {
  var PAGINA = 50, datos = [], vista = [], mostrados = 0;
  var orden = { campo: 'score', asc: false };
  var tbody = document.querySelector('#resultados tbody');
  var resumen = document.getElementById('resumen');
  var campos = [].slice.call(document.querySelectorAll('[data-campo]'));
  var mas = document.getElementById('mas');

  var COP = new Intl.NumberFormat('es-CO');
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function estado() {
    var o = {};
    campos.forEach(function (el) { if (el.value) o[el.dataset.campo] = el.value; });
    return o;
  }

  function aplicar() {
    var f = estado();
    var q = (f.q || '').toLowerCase().trim();
    var vmin = f.vmin ? +f.vmin : null, vmax = f.vmax ? +f.vmax : null;
    vista = datos.filter(function (c) {
      if (f.departamento && c.dep !== f.departamento) return false;
      if (f.municipio && c.mun !== f.municipio) return false;
      if (f.entidad && c.e !== f.entidad) return false;
      if (f.anio && String(c.a) !== f.anio) return false;
      if (f.periodo && c.per !== f.periodo) return false;
      if (f.tipo && c.t !== f.tipo) return false;
      if (f.modalidad && c.m !== f.modalidad) return false;
      if (f.bandera && c.f.indexOf(f.bandera) === -1) return false;
      if (vmin != null && c.v < vmin) return false;
      if (vmax != null && c.v > vmax) return false;
      if (q && (c.d + ' ' + c.e + ' ' + c.pv + ' ' + c.id).toLowerCase().indexOf(q) === -1) return false;
      return true;
    });
    var k = { descripcion: 'd', entidad: 'e', municipio: 'munv', anio: 'a',
              valor: 'v', fuertes: 'nf', score: 's' }[orden.campo];
    vista.sort(function (a, b) {
      var x = a[k], y = b[k], r = typeof x === 'number' ? x - y : String(x).localeCompare(String(y), 'es');
      return orden.asc ? r : -r;
    });
    mostrados = 0; tbody.innerHTML = '';
    pintar();
    var suma = vista.reduce(function (s, c) { return s + c.v; }, 0);
    resumen.textContent = COP.format(vista.length) + ' de ' + COP.format(datos.length) +
      ' contratos marcados · ' + plata(suma) + ' en total';
    sincronizarURL(f);
  }

  function pintar() {
    var lote = vista.slice(mostrados, mostrados + PAGINA);
    tbody.insertAdjacentHTML('beforeend', lote.map(function (c) {
      return '<tr><td><a href="' + c.u + '">' + esc(c.d) + '</a><small>' + esc(c.pv) + '</small></td>' +
        '<td>' + esc(c.e) + '</td><td>' + esc(c.munv) + '</td>' +
        '<td class="num">' + esc(c.a) + '</td><td class="num">' + plata(c.v) + '</td>' +
        '<td class="num">' + c.nf + '</td><td class="num">' + c.s.toFixed(2).replace('.', ',') + '</td></tr>';
    }).join(''));
    mostrados += lote.length;
    mas.hidden = mostrados >= vista.length;
    mas.textContent = 'Ver mas (' + COP.format(vista.length - mostrados) + ' restantes)';
  }

  function sincronizarURL(f) {
    var u = new URL(location.href);
    u.search = '';
    Object.keys(f).forEach(function (k) { u.searchParams.set(k, f[k]); });
    if (orden.campo !== 'score' || orden.asc) {
      u.searchParams.set('orden', orden.campo);
      if (orden.asc) u.searchParams.set('asc', '1');
    }
    history.replaceState(null, '', u.pathname + (u.search || ''));
  }

  function desdeURL() {
    var p = new URL(location.href).searchParams;
    campos.forEach(function (el) {
      var v = p.get(el.dataset.campo);
      if (v != null) el.value = v;
    });
    if (p.get('orden')) orden = { campo: p.get('orden'), asc: p.get('asc') === '1' };
    marcarOrden();
  }
  function marcarOrden() {
    [].forEach.call(document.querySelectorAll('#resultados th[data-orden]'), function (th) {
      if (th.dataset.orden === orden.campo) th.setAttribute('aria-sort', orden.asc ? 'ascending' : 'descending');
      else th.removeAttribute('aria-sort');
    });
  }

  document.getElementById('exportar').addEventListener('click', function () {
    var cols = ['id_contrato', 'objeto', 'entidad', 'departamento', 'municipio', 'proveedor',
                'anio', 'periodo_gobierno', 'tipo_contrato', 'modalidad', 'valor_plausible',
                'score', 'n_banderas_fuertes', 'banderas', 'url_secop', 'ficha_plomada'];
    var esq = function (v) { return '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"'; };
    var filas = vista.map(function (c) {
      return [c.id, c.d, c.e, c.dep, c.mun, c.pv, c.a, c.per, c.t, c.m, c.v, c.s, c.nf,
              c.f.join(' '), c.url, location.origin + c.u].map(esq).join(',');
    });
    // BOM para que Excel en es-CO no destroce las tildes
    var blob = new Blob(['﻿' + cols.join(',') + '\n' + filas.join('\n')],
                        { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'plomada-contratos-' + vista.length + '.csv';
    a.click(); URL.revokeObjectURL(a.href);
  });

  document.getElementById('limpiar').addEventListener('click', function () {
    campos.forEach(function (el) { el.value = ''; });
    orden = { campo: 'score', asc: false }; marcarOrden(); aplicar();
  });
  campos.forEach(function (el) {
    el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', aplicar);
  });
  [].forEach.call(document.querySelectorAll('#resultados th[data-orden]'), function (th) {
    th.addEventListener('click', function () {
      var c = th.dataset.orden;
      orden = { campo: c, asc: orden.campo === c ? !orden.asc : c === 'descripcion' };
      marcarOrden(); aplicar();
    });
  });
  mas.addEventListener('click', pintar);

  fetch('/datos/contratos.json').then(function (r) { return r.json(); }).then(function (d) {
    datos = d; desdeURL(); aplicar();
  }).catch(function () { resumen.textContent = 'No se pudieron cargar los datos.'; });
})();
