"""Textos editoriales largos. Separados del generador para que se puedan
corregir sin tocar codigo. Nada aqui afirma que alguien cometio un delito.

El texto que ve el lector va con su ortografia completa (tildes y enes).
Lo que NO lleva tildes es lo que viene del pipeline en MAYUSCULAS (nombres
de entidad, municipio, departamento) y los identificadores de columna
(<code>valor_plausible</code>, <code>f_cuenta_compartida</code>): esos son
datos y nombres de campo, no prosa, y se citan tal como salen de la fuente.
"""

AVISO = ("Un indicio no es una acusación. Todo lo que aparece aquí es un <strong>indicio</strong> "
         "calculado sobre datos públicos del SECOP II para priorizar revisión. "
         "No afirma que persona o entidad alguna haya obrado de forma irregular.")

AVISO_CORTO = "Indicio para revisión, no acusación."

FALSOS_POSITIVOS = [
    ("Juntas de Acción Comunal con cuenta compartida",
     "Las JAC de un mismo municipio comparten cuenta bancaria porque la alcaldía "
     "canaliza los pagos por una sola tesorería. La bandera de cuenta compartida se "
     "encendía sin que hubiera nada que revisar.",
     "Se clasifica con <code>ev_tipo_red_cuenta</code>, y cada caso enciende (o no) "
     "una bandera distinta: <code>empresas_independientes</code> enciende "
     "<code>f_cuenta_compartida</code> (indicio fuerte); <code>consorcios</code> "
     "enciende una bandera aparte y más débil, <code>f_cuenta_consorcios</code>; y "
     "<code>comunitaria</code> no enciende ninguna bandera — es ruido administrativo "
     "conocido, no un indicio ni siquiera atenuado."),
    ("Convenios interadministrativos leídos como obra directa",
     "Cuando el Estado le contrata al Estado, la contratación directa está autorizada "
     "por el artículo 2 de la ley 1150 de 2007. Estos convenios eran el 26% de los "
     "falsos positivos de la bandera de obra por contratación directa.",
     "Se excluyen del conteo los procesos en los que contratante y contratista son "
     "ambos entidades públicas. El contrato sigue siendo consultable, pero la bandera "
     "no se enciende."),
    ("Consorcios y uniones temporales con cuenta del líder",
     "En un consorcio la cuenta de pago suele estar a nombre de la empresa líder. "
     "Eso hace que varios NIT compartan cuenta sin que exista simulación de competencia.",
     "Enciende <code>f_cuenta_consorcios</code>, una bandera propia y de peso bajo "
     "(no una versión atenuada de <code>f_cuenta_compartida</code>), presentada "
     "siempre con la razón a la vista."),
    ("Valores de publicación imposibles",
     "24 contratos están publicados con cifras aritméticamente imposibles, hasta "
     "6 x 10<sup>18</sup> pesos, más que el PIB mundial. Concentraban el 98,6% del "
     "total agregado y distorsionaban cualquier ranking por dinero.",
     "No se borran: se muestran como falla de publicación de la entidad. Todo el "
     "dinero de este sitio se suma con <code>valor_plausible</code>, la versión "
     "saneada, nunca con <code>valor</code>."),
    ("Municipios pequeños encabezando el ranking por azar",
     "Un municipio con 4 contratos y 2 marcados da 50% de tasa cruda y encabezaría "
     "cualquier lista ordenada por porcentaje, sin que eso signifique nada.",
     "Todos los rankings se ordenan por <code>tasa_ajustada</code>, que aplica "
     "contracción bayesiana hacia la tasa nacional. La tasa cruda se muestra al lado "
     "para que la corrección sea visible y auditable."),
]

LIMITACIONES = [
    ("Cobertura desigual de identificadores",
     "El análisis de red solo puede calcularse sobre los contratos que traen el "
     "identificador. Es un piso, no un censo: si una relación no aparece, puede ser "
     "porque no existe o porque el dato no fue publicado."),
    ("Municipio sin definir",
     "Una parte de los contratos trae <code>NO DEFINIDO</code> en el campo de ciudad. "
     "Se tratan como dato ausente y no se pintan en el mapa ni se atribuyen a ningún "
     "municipio."),
    ("El universo es obra pública, no toda la contratación",
     "De 5.975.627 contratos del SECOP II se analizan 77.864 de obra, interventoría, "
     "consultoría, APP y concesión. Los 5.123.891 de prestación de servicios quedan "
     "fuera del alcance de este trabajo."),
    ("Las banderas describen patrones, no intenciones",
     "Cada bandera responde a una pregunta verificable sobre el expediente publicado. "
     "Ninguna responde por qué ocurrió lo que ocurrió. Esa respuesta requiere reportería."),
    ("Los datos son una foto del SECOP II en la fecha de corte",
     "Un contrato puede haberse modificado, liquidado o caído después del corte. "
     "El enlace a la fuente oficial está en cada ficha justamente para eso."),
]

PUNTAJE = """
<p>El puntaje no es una probabilidad de irregularidad ni el resultado de un modelo
entrenado. Es una suma explicable, y esa es una decisión deliberada: un puntaje de
caja negra no se puede defender ante un editor ni ante un juez.</p>
<ol>
  <li>Cada una de las banderas responde a una pregunta objetiva sobre el expediente
      publicado, del tipo <em>cuántas ofertas recibió este proceso</em>. La respuesta
      sale del dato, no de un criterio.</li>
  <li>Cada bandera encendida aporta su <strong>peso</strong>. Los pesos están en
      <code>banderas_glosario.csv</code> y se pueden auditar uno por uno.</li>
  <li>La suma es <code>puntos_crudos</code>. El <code>score</code> es esa suma
      normalizada a 0&ndash;1 para poder comparar contratos entre sí.</li>
  <li>Un contrato entra al conjunto de <strong>atípicos</strong> cuando acumula
      señales fuertes, no por un puntaje alto compuesto de muchas señales débiles.
      Diez indicios menores no equivalen a uno grave.</li>
</ol>
<p>El umbral está donde está por una razón práctica: más abajo, el volumen de
contratos marcados deja de ser revisable por un equipo humano y la herramienta
pierde su utilidad; más arriba, se pierden casos que sí ameritan revisión. Es un
punto de corte operativo, no una frontera entre lo lícito y lo ilícito.</p>
"""

INTRO_METODOLOGIA = """
<p>Esta página existe para que cualquiera pueda desarmar lo que hicimos. Es la parte
del proyecto que dice lo que <strong>no</strong> podemos afirmar.</p>
<p>Plomada lee la contratación de obra pública del Estado colombiano publicada en el
SECOP II, la plataforma oficial. Todos los datos son públicos y no hay en este sitio
ninguna información filtrada, reservada ni obtenida por fuera de los canales
oficiales. Lo que aportamos no es información nueva: es una forma de mirarla.</p>
<p>La diferencia con un buscador de contratos es el sujeto. Un buscador organiza la
información por empresa, y la empresa es lo más fácil de cambiar: se disuelve y al
día siguiente aparece otra con otro NIT. Plomada organiza la información por las
personas que firman &mdash; ordenador del gasto, supervisor, representante legal,
ordenador de pago &mdash; porque una cédula no se disuelve.</p>
"""

PRIVACIDAD = """
<p>Este sitio conecta por identificadores personales pero <strong>no los publica</strong>.
Nunca salen del pipeline hacia una página, una descarga o una respuesta:</p>
<ul>
  <li>Números de cuenta bancaria, en cualquier forma.</li>
  <li>La cédula del representante legal y la del supervisor, que son particulares.</li>
  <li>El documento del contratista cuando es persona natural.</li>
  <li>La cédula del ordenador del gasto. Es un funcionario público en ejercicio y su
      <em>nombre</em> sí es información pública, pero el número no aporta nada al
      lector y sí aporta riesgo.</li>
</ul>
<p>Lo que sí se publica es el <em>hecho</em> de la relación. &laquo;Tres proveedores
comparten cuenta bancaria&raquo; es publicable y es exactamente el indicio; el número
de la cuenta no lo es, y no lo será. Esto no es una política escrita: es un
serializador en la capa de datos y una prueba automática que tumba la publicación del
sitio si una columna prohibida alcanza a llegar a un archivo.</p>
"""

FUENTES = """
<ul>
  <li><a href="https://www.colombiacompra.gov.co/transparencia/conjuntos-de-datos-abiertos"
      rel="noopener">SECOP II &mdash; datos abiertos de Colombia Compra Eficiente</a>,
      fuente primaria de todos los contratos.</li>
  <li><a href="https://www.dane.gov.co/index.php/servicios-al-ciudadano/servicios-informacion/codigos-estadisticos"
      rel="noopener">DIVIPOLA y Marco Geoestadístico Nacional del DANE</a>,
      fronteras y códigos de departamento y municipio.</li>
  <li><a href="/datos/">Datos derivados de este sitio</a>, en CSV, ya saneados de
      identificadores personales.</li>
</ul>
"""
