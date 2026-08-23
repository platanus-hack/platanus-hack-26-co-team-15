/* Mapa satelital de la ficha de contrato. Click-to-load (Tanda B, B6): las
   imagenes las sirve Esri (server.arcgisonline.com), y eso no se puede
   vendorizar -- son imagenes satelitales del mundo. Pero pedirlas SOLAS al
   abrir la ficha le dice a Esri, sin que el lector lo sepa, que coordenadas
   esta mirando. El publico de este sitio son periodistas: eso delata interes
   investigativo a un tercero. Por eso no se pide nada hasta el clic.

   El popup se arma con DOM/createElement/textContent, nunca interpolando
   HTML en un string (test_privacy.py lo verifica: nada de asignar
   contenido HTML crudo ni de un template literal armando markup). Lee
   lat/lon/direccion de atributos
   data-* (ya escapados por el generador). */
(function () {
  var contenedor = document.getElementById('mapa-satelital');
  if (!contenedor) return;
  var lat = parseFloat(contenedor.dataset.lat), lon = parseFloat(contenedor.dataset.lon);
  if (isNaN(lat) || isNaN(lon)) return;
  var direccion = contenedor.dataset.direccion || '';
  var boton = contenedor.querySelector('button');
  if (!boton) return;

  boton.addEventListener('click', function () {
    contenedor.classList.remove('mapa-placeholder');
    contenedor.replaceChildren();  // limpia el placeholder por DOM, nunca con un string de HTML

    var mapa = L.map(contenedor, { scrollWheelZoom: false }).setView([lat, lon], 15);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19,
      attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, ' +
        'Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
    }).addTo(mapa);

    var popup = document.createElement('div');
    var b = document.createElement('b');
    b.textContent = 'Ubicacion de ejecucion:';
    popup.appendChild(b);
    popup.appendChild(document.createElement('br'));
    popup.appendChild(document.createTextNode(direccion));

    L.marker([lat, lon]).addTo(mapa).bindPopup(popup).openPopup();
  }, { once: true });
})();
