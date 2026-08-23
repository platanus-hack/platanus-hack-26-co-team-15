"""Textos editoriales largos. Separados del generador para que se puedan
corregir sin tocar codigo. Nada aqui afirma que alguien cometio un delito.
"""

AVISO = ("Un indicio no es una acusacion. Todo lo que aparece aqui es un <strong>indicio</strong> "
         "calculado sobre datos publicos del SECOP II para priorizar revision. "
         "No afirma que persona o entidad alguna haya obrado de forma irregular.")

AVISO_CORTO = "Indicio para revision, no acusacion."

FALSOS_POSITIVOS = [
    ("Juntas de Accion Comunal con cuenta compartida",
     "Las JAC de un mismo municipio comparten cuenta bancaria porque la alcaldia "
     "canaliza los pagos por una sola tesoreria. La bandera de cuenta compartida se "
     "encendia sin que hubiera nada que revisar.",
     "Se clasifica con <code>ev_tipo_red_cuenta</code>, y cada caso enciende (o no) "
     "una bandera distinta: <code>empresas_independientes</code> enciende "
     "<code>f_cuenta_compartida</code> (indicio fuerte); <code>consorcios</code> "
     "enciende una bandera aparte y mas debil, <code>f_cuenta_consorcios</code>; y "
     "<code>comunitaria</code> no enciende ninguna bandera — es ruido administrativo "
     "conocido, no un indicio ni siquiera atenuado."),
    ("Convenios interadministrativos leidos como obra directa",
     "Cuando el Estado le contrata al Estado, la contratacion directa esta autorizada "
     "por el articulo 2 de la ley 1150 de 2007. Estos convenios eran el 26% de los "
     "falsos positivos de la bandera de obra por contratacion directa.",
     "Se excluyen del conteo los procesos en los que contratante y contratista son "
     "ambos entidades publicas. El contrato sigue siendo consultable, pero la bandera "
     "no se enciende."),
    ("Consorcios y uniones temporales con cuenta del lider",
     "En un consorcio la cuenta de pago suele estar a nombre de la empresa lider. "
     "Eso hace que varios NIT compartan cuenta sin que exista simulacion de competencia.",
     "Enciende <code>f_cuenta_consorcios</code>, una bandera propia y de peso bajo "
     "(no una version atenuada de <code>f_cuenta_compartida</code>), presentada "
     "siempre con la razon a la vista."),
    ("Valores de publicacion imposibles",
     "24 contratos estan publicados con cifras aritmeticamente imposibles, hasta "
     "6 x 10<sup>18</sup> pesos, mas que el PIB mundial. Concentraban el 98,6% del "
     "total agregado y distorsionaban cualquier ranking por dinero.",
     "No se borran: se muestran como falla de publicacion de la entidad. Todo el "
     "dinero de este sitio se suma con <code>valor_plausible</code>, la version "
     "saneada, nunca con <code>valor</code>."),
    ("Municipios pequenos encabezando el ranking por azar",
     "Un municipio con 4 contratos y 2 marcados da 50% de tasa cruda y encabezaria "
     "cualquier lista ordenada por porcentaje, sin que eso signifique nada.",
     "Todos los rankings se ordenan por <code>tasa_ajustada</code>, que aplica "
     "contraccion bayesiana hacia la tasa nacional. La tasa cruda se muestra al lado "
     "para que la correccion sea visible y auditable."),
]

LIMITACIONES = [
    ("Cobertura desigual de identificadores",
     "El analisis de red solo puede calcularse sobre los contratos que traen el "
     "identificador. Es un piso, no un censo: si una relacion no aparece, puede ser "
     "porque no existe o porque el dato no fue publicado."),
    ("Municipio sin definir",
     "Una parte de los contratos trae <code>NO DEFINIDO</code> en el campo de ciudad. "
     "Se tratan como dato ausente y no se pintan en el mapa ni se atribuyen a ningun "
     "municipio."),
    ("El universo es obra publica, no toda la contratacion",
     "De 5.975.627 contratos del SECOP II se analizan 77.864 de obra, interventoria, "
     "consultoria, APP y concesion. Los 5.123.891 de prestacion de servicios quedan "
     "fuera del alcance de este trabajo."),
    ("Las banderas describen patrones, no intenciones",
     "Cada bandera responde a una pregunta verificable sobre el expediente publicado. "
     "Ninguna responde por que ocurrio lo que ocurrio. Esa respuesta requiere reporteria."),
    ("Los datos son una foto del SECOP II en la fecha de corte",
     "Un contrato puede haberse modificado, liquidado o caido despues del corte. "
     "El enlace a la fuente oficial esta en cada ficha justamente para eso."),
]

PUNTAJE = """
<p>El puntaje no es una probabilidad de irregularidad ni el resultado de un modelo
entrenado. Es una suma explicable, y esa es una decision deliberada: un puntaje de
caja negra no se puede defender ante un editor ni ante un juez.</p>
<ol>
  <li>Cada una de las banderas responde a una pregunta objetiva sobre el expediente
      publicado, del tipo <em>cuantas ofertas recibio este proceso</em>. La respuesta
      sale del dato, no de un criterio.</li>
  <li>Cada bandera encendida aporta su <strong>peso</strong>. Los pesos estan en
      <code>banderas_glosario.csv</code> y se pueden auditar uno por uno.</li>
  <li>La suma es <code>puntos_crudos</code>. El <code>score</code> es esa suma
      normalizada a 0&ndash;1 para poder comparar contratos entre si.</li>
  <li>Un contrato entra al conjunto de <strong>atipicos</strong> cuando acumula
      senales fuertes, no por un puntaje alto compuesto de muchas senales debiles.
      Diez indicios menores no equivalen a uno grave.</li>
</ol>
<p>El umbral esta donde esta por una razon practica: mas abajo, el volumen de
contratos marcados deja de ser revisable por un equipo humano y la herramienta
pierde su utilidad; mas arriba, se pierden casos que si ameritan revision. Es un
punto de corte operativo, no una frontera entre lo licito y lo ilicito.</p>
"""

INTRO_METODOLOGIA = """
<p>Esta pagina existe para que cualquiera pueda desarmar lo que hicimos. Es la parte
del proyecto que dice lo que <strong>no</strong> podemos afirmar.</p>
<p>Plomada lee la contratacion de obra publica del Estado colombiano publicada en el
SECOP II, la plataforma oficial. Todos los datos son publicos y no hay en este sitio
ninguna informacion filtrada, reservada ni obtenida por fuera de los canales
oficiales. Lo que aportamos no es informacion nueva: es una forma de mirarla.</p>
<p>La diferencia con un buscador de contratos es el sujeto. Un buscador organiza la
informacion por empresa, y la empresa es lo mas facil de cambiar: se disuelve y al
dia siguiente aparece otra con otro NIT. Plomada organiza la informacion por las
personas que firman &mdash; ordenador del gasto, supervisor, representante legal,
ordenador de pago &mdash; porque una cedula no se disuelve.</p>
"""

PRIVACIDAD = """
<p>Este sitio conecta por identificadores personales pero <strong>no los publica</strong>.
Nunca salen del pipeline hacia una pagina, una descarga o una respuesta:</p>
<ul>
  <li>Numeros de cuenta bancaria, en cualquier forma.</li>
  <li>La cedula del representante legal y la del supervisor, que son particulares.</li>
  <li>El documento del contratista cuando es persona natural.</li>
  <li>La cedula del ordenador del gasto. Es un funcionario publico en ejercicio y su
      <em>nombre</em> si es informacion publica, pero el numero no aporta nada al
      lector y si aporta riesgo.</li>
</ul>
<p>Lo que si se publica es el <em>hecho</em> de la relacion. &laquo;Tres proveedores
comparten cuenta bancaria&raquo; es publicable y es exactamente el indicio; el numero
de la cuenta no lo es, y no lo sera. Esto no es una politica escrita: es un
serializador en la capa de datos y una prueba automatica que tumba la publicacion del
sitio si una columna prohibida alcanza a llegar a un archivo.</p>
"""

FUENTES = """
<ul>
  <li><a href="https://www.colombiacompra.gov.co/transparencia/conjuntos-de-datos-abiertos"
      rel="noopener">SECOP II &mdash; datos abiertos de Colombia Compra Eficiente</a>,
      fuente primaria de todos los contratos.</li>
  <li><a href="https://www.dane.gov.co/index.php/servicios-al-ciudadano/servicios-informacion/codigos-estadisticos"
      rel="noopener">DIVIPOLA y Marco Geoestadistico Nacional del DANE</a>,
      fronteras y codigos de departamento y municipio.</li>
  <li><a href="/datos/">Datos derivados de este sitio</a>, en CSV, ya saneados de
      identificadores personales.</li>
</ul>
"""
