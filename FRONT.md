# Plomada — Brief para el equipo de Frontend

Eres parte del equipo que construye la cara pública de **Plomada**, un proyecto de
periodismo de datos sobre corrupción en obra pública en Colombia. Este documento te
da todo el contexto que necesitas y lo que tienes que implementar. **El stack lo
eliges tú.**

Lee esto completo antes de escribir una línea de código. El contexto no es adorno:
varias decisiones de diseño solo tienen sentido si entiendes por qué existe el
proyecto.

---

## 1. Qué es Plomada

Una plomada es el instrumento que usan los constructores para revelar lo que está
torcido. Eso es el proyecto: detectar **indicios de irregularidad** en la
contratación de obra pública del Estado colombiano, y exponerlos de forma que un
periodista, una veeduría o un ciudadano pueda actuar.

Los datos son 100% públicos, del **SECOP II** (la plataforma oficial de
contratación estatal). No hay nada filtrado ni privado.

### El problema con lo que ya existe

Hay buscadores de contratos (BuscaSECOP y similares). Son **buscadores de filas**:
buscas un NIT y ves sus contratos. El problema es que la empresa es la máscara —
es lo más fácil de cambiar. Si investigan a una constructora, se cierra y mañana
aparece otra con otro nombre y otro NIT.

**Plomada sigue personas, no empresas.** En cada contrato hay cuatro cédulas que
nadie está mirando:

- **Ordenador del gasto** — el funcionario que autorizó gastar la plata
- **Supervisor** — el que debía vigilar que la obra se hiciera
- **Representante legal** de la empresa contratista
- **Ordenador de pago** — el que autorizó el desembolso

Una empresa se disuelve; una cédula no. Ahí está la diferencia.

### Lo que eso permite ver

- **El funcionario que se muda**: un ordenador cambia de alcaldía y sus mismos
  contratistas aparecen allá. Buscando por empresa son dos historias separadas.
- **Empresas que son la misma persona**: tres "competidores" en una licitación con
  NITs distintos que comparten representante legal, dirección o cuenta bancaria.
  Esa licitación no tuvo competencia, tuvo una puesta en escena.
- **El supervisor imposible**: una cédula supervisando 200 obras a la vez no está
  supervisando nada.
- **El interventor que es socio del constructor**: el interventor es el control
  independiente de la obra. Si está en la misma red que el constructor, el control
  no existe. Es el mecanismo central del fraude en obra pública en Colombia.

---

## 2. Las reglas del proyecto (aplican a tu código)

**Riesgo ≠ fraude.** Nada de lo que muestres afirma que alguien es corrupto.
Todo es un *indicio* para priorizar investigación. Esto no es una sutileza legal:
es la diferencia entre un proyecto que sobrevive y uno que se cae en una demanda.

- Usa siempre: "señal de riesgo", "indicio", "contrato atípico", "amerita revisión".
- **Nunca** uses: "corrupto", "fraude", "delito", "robo", "culpable".

**Sin evidencia no se publica.** Cada bandera que muestres debe venir acompañada del
número que la disparó y del enlace a la fuente oficial. Un score suelto no sirve.

**Los identificadores personales conectan, no se muestran.** Ver sección 5. Esto es
una restricción de código, no una recomendación.

**El norte del proyecto**: que la alerta llegue **antes** de que se adjudique, no
después. Una autopsia bien hecha no cambia nada.

---

## 3. Las cifras (úsalas, están verificadas)

| Dato | Valor |
|---|---|
| Contratos en SECOP II (todo) | 5.975.627 |
| ...de los cuales son prestación de servicios | 5.123.891 |
| **Universo de obra pública** | **77.864 contratos** |
| **Valor total** | **$209 billones COP** |
| **Contratos atípicos detectados** | **11.121 (14,3%)** |
| **Valor de los atípicos** | **$11,7 billones** |
| Municipios en el ranking | 721 |
| Administraciones (entidad × periodo) | 1.397 |
| Departamentos | 34 |

Composición del universo: Obra 52.355 · Interventoría 13.074 · Consultoría 11.482 ·
APP 715 · Concesión 238.

Casos concretos que sirven para diseñar y para demos:

- **El Bagre, Antioquia**: 256 contratos, 78,8% atípicos
- **ICCU de Cundinamarca**: 2.229 contratos, 75,2% atípicos, $500 mil millones
- **Un ordenador del gasto**: 52 contratos, $1,75 billones, **99,8% a un solo
  proveedor**
- **Un representante legal** figura en **24 empresas** proveedoras
- **MYG LINARES** y **MYG PUERRES** comparten cuenta bancaria en municipios distintos

---

## 4. Contrato de datos

Recibes CSVs en `out/`. **Estos encabezados son el contrato: no cambian.**

### `contratos_atipicos.csv` — 11.121 filas, 1 fila = 1 contrato

Identidad y contexto:
`id_contrato` · `nit_entidad` · `entidad` · `departamento` · `ciudad` · `orden` ·
`tipo_contrato` · `modalidad` · `estado` · `unspsc` · `fecha_firma` · `anio` ·
`periodo_gobierno` · `descripcion` · `dir_ejecucion` · `urlproceso`

Dinero: `valor` · `valor_plausible` · `valor_pagado` · `valor_pend_ejecucion` ·
`valor_anticipo` · `precio_base`
Fuente de recursos: `rec_regalias` · `rec_sgp` · `rec_propios_terr`
Competencia: `n_oferentes_unicos` · `n_invitados` · `dias_ventana`
Plazos: `dias_originales` · `dias_adicionados`
Personas: `proveedor` · `ordenador` · `supervisor` (nombres) + sus `doc_*` (**ver
sección 5**)
Puntaje: `puntos_crudos` · `score` (0–1) · `n_banderas_fuertes` · `es_atipico`
Banderas: 21 columnas booleanas `f_*`
Evidencia: 10 columnas `ev_*`

### `ranking_municipios.csv` — 721 filas

`departamento` · `ciudad` · `n_contratos` · `n_atipicos` · `valor_total` ·
`valor_atipico` · `regalias_atipicas` · `score_medio` · `tasa_cruda` ·
**`tasa_ajustada`** · `share_valor_atipico` · `alpha` · `beta` + conteos por bandera
(`n_proponente_unico`, `n_obra_directa`, `n_cuenta_compartida`, `n_fraccionamiento`,
`n_anticipo_no_declarado`, `n_sobrepago`)

**Ordena y colorea SIEMPRE por `tasa_ajustada`, nunca por `tasa_cruda`.**
Un municipio con 4 contratos y 2 marcados da 50% crudo y encabezaría la lista por
puro azar. La tasa ajustada corrige eso con estadística. Muestra las dos juntas para
que se vea la corrección — eso genera confianza, no la esconde.

### `ranking_administraciones.csv` — 1.397 filas
`nit_entidad` · `entidad` · `departamento` · `ciudad` · `orden` · `periodo_gobierno`
· `n_contratos` · `n_atipicos` · `valor_total` · `valor_atipico` · `score_medio` ·
`tasa_cruda` · `tasa_ajustada` · `share_valor_atipico`

Periodos: `2016-2019`, `2020-2023`, `2024-2027` (periodos de alcaldes y gobernadores).

### `ranking_departamentos.csv` — 34 filas
Mismas columnas, agregado por departamento. Es la capa base del mapa.

### `banderas_glosario.csv` — 21 filas
`bandera` · `peso` · `grupo` · `glosa`

**Esta es la única fuente de verdad para nombres y textos de banderas.** No
inventes tus propios nombres ni escribas las glosas a mano en el código: lee este
archivo. Si el pipeline agrega una bandera, tu UI debe absorberla sola.


---

## 5. Restricciones de privacidad — esto va en código

Hay una capa que **tiene que existir antes de cualquier build público**: un
serializador que elimine columnas prohibidas.

**Nunca se publican, en ninguna respuesta ni en ningún render:**

- `cuenta_key` y cualquier número de cuenta bancaria
- `doc_replegal`, `doc_supervisor` (cédulas de particulares)
- `doc_proveedor` cuando es persona natural

**Sí se publica** el *hecho* de la relación: "3 proveedores comparten cuenta
bancaria" es publicable; el número de cuenta no lo es, jamás.

**Zona gris**: `doc_ordenador`. Es un funcionario público en ejercicio, lo cual es
distinto — pero muestra el **nombre** (`ordenador`), no el número.

**Implementa esto como un test que tumbe el build** si una columna de la lista negra
aparece en una respuesta o en un artefacto estático. Si esto queda "para después",
se filtra.

---

## 6. Trampas de los datos (te van a morder si no las conoces)

**1. Los textos vienen en MAYÚSCULAS sin tildes.** El pipeline normaliza para poder
comparar: verás `GOBERNACION DEL CHOCO`, `EL CARMEN DE VIBORAL`. Necesitas una
función de presentación que haga title-case y no destroce las siglas (`ICCU`,
`ANI`, `SENA`, `E.S.E.`, `S.A.S.`). No lo resuelvas caso por caso en cada
componente.

**2. `urlproceso` no es una URL, es un struct serializado.** Llega literalmente así:

```
{'url': 'https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.5056481&isFromPublicArea=True...'}
```

Extráela una sola vez, en la capa de datos. **Este enlace es obligatorio en la
ficha de contrato**: sin poder verificar en la fuente oficial, el proyecto no es
creíble.

**3. `'NO DEFINIDO'` es un placeholder frecuente**, sobre todo en `ciudad`. No lo
pintes como si fuera un municipio. Trátalo como dato ausente.

**4. Cobertura desigual por campo.** No asumas que todo está lleno:

| Campo | Cobertura |
|---|---|
| `dir_ejecucion` | 100% |
| `doc_proveedor` | 87,4% |
| `doc_ordenador` | 64,5% |
| `doc_supervisor` | 54,3% |
| `doc_replegal` | 30,9% |
| cuenta bancaria | 23,7% |

Cuando muestres un análisis de red, di sobre qué fracción se calculó. "Un piso, no
un censo" es la formulación honesta.

**5. Usa `valor_plausible`, no `valor`, para sumar dinero.** Hay 24 contratos
publicados con cifras imposibles (hasta 6×10¹⁸ COP, más que el PIB mundial) que
concentraban el 98,6% del "total". `valor_plausible` es el saneado. Los 24 se
muestran como falla de publicación, no se borran.

**6. Formato de moneda colombiano.** Las cifras son enormes: `$209.043.881.234.567`
es ilegible. Usa "$209 billones", "$500 mil millones", "$63,5 mil millones". Ojo:
en Colombia *billón* = 10¹², no 10⁹.

---

## 7. Qué tienes que implementar

Cuatro vistas. **Están en orden de prioridad y la número 1 es la que define el
producto.**

### 7.1 Ficha de contrato — LO MÁS IMPORTANTE

No es una tabla de campos. Es un argumento verificable. Para un `id_contrato`:

- Encabezado: entidad, municipio, valor, año, tipo, modalidad, proveedor
- **Las banderas encendidas, cada una con su evidencia numérica**. No "score 0,42",
  sino: *"Proponente único — este proceso recibió 1 oferta"*, *"Supervisor
  sobrecargado — esta persona tiene 47 contratos a cargo"*, *"Fraccionamiento —
  3 contratos hermanos al mismo proveedor en 30 días"*
- Las banderas agrupadas por `grupo` (Competencia, Red, Dinero, Umbrales,
  Ejecución, Opacidad) y ordenadas por `peso` descendente
- **Enlace prominente a `urlproceso`** — "Verificar en SECOP II"
- Un aviso permanente y visible: esto es un indicio, no una acusación

Las columnas `ev_*` existen exactamente para esto:

| Columna | Qué contiene |
|---|---|
| `ev_share_top1_ordenador` | % del valor del ordenador que fue a un solo proveedor |
| `ev_hhi_ordenador` | Índice de concentración (0–1) |
| `ev_contratos_supervisor` | Cuántos contratos tiene ese supervisor |
| `ev_entidades_ordenador` | En cuántas entidades ha firmado |
| `ev_proveedores_por_cuenta` | Cuántos proveedores comparten esa cuenta |
| `ev_tipo_red_cuenta` | `empresas_independientes` / `consorcios` / `comunitaria` |
| `ev_empresas_por_replegal` | Empresas con el mismo representante legal |
| `ev_hermanos_30d` | Contratos hermanos en 30 días |
| `ev_ventana_mediana_modalidad` | Días mediana de su modalidad, para comparar |
| `ev_tope_minima_entidad` | Techo de mínima cuantía de esa entidad |

Sobre `ev_tipo_red_cuenta`: solo `empresas_independientes` es indicio fuerte.
`consorcios` es esperable (la cuenta del consorcio suele estar a nombre del líder)
y `comunitaria` es ruido administrativo. **Si tratas los tres igual, publicas
falsos positivos.**

### 7.2 Mapa

Coroplético de Colombia por `tasa_ajustada`. Dos niveles: departamento (34) y
municipio (721). Al hacer clic, panel con el detalle y los contratos atípicos de ese
municipio.

Necesitas fronteras administrativas oficiales (Marco Geoestadístico Nacional del
DANE). El cruce entre el campo `ciudad` (texto libre) y los códigos oficiales
DIVIPOLA lo está resolviendo otro frente del equipo — **coordina con ellos, no
armes tu propio mapeo de nombres.**

### 7.3 Buscador y listado

Filtros por departamento, municipio, entidad, año, periodo de gobierno, tipo,
modalidad, rango de valor, y por bandera específica. Ordenable. Con exportar a CSV
— si el proyecto es bien público, la gente tiene que poder llevarse los datos.

### 7.4 Página de metodología

**Esto es producto, no documentación.** Es la defensa legal y de credibilidad del
proyecto:

- Las 21 banderas con su peso, su glosa y la norma que la sustenta
- Cómo se calcula el puntaje y por qué el umbral está donde está
- **Los falsos positivos conocidos y qué se hizo con ellos.** Ejemplos reales:
  las Juntas de Acción Comunal comparten cuenta bancaria porque el municipio
  canaliza pagos, no porque sean un cartel; los convenios interadministrativos
  (cuando el Estado le contrata al Estado) usan contratación directa por vía legal
  y eran el 26% de los falsos positivos de una bandera
- Las limitaciones de cobertura de la sección 6
- Enlace a los datos crudos y al código

Contarás lo que el proyecto **no** puede afirmar. Eso no lo debilita: es lo que lo
hace defendible.

---

## 8. Stack: tú decides

Libre elección. Solo tres condiciones no negociables:

1. **Las URLs son compartibles.** Un contrato, un municipio y una búsqueda con
   filtros tienen que tener cada uno su propia URL. Un periodista necesita poder
   mandar un enlace.
2. **El mapa y las listas cargan rápido y son indexables por buscadores.** Es un
   proyecto de interés público: si Google no lo encuentra, no existe.
3. **La capa de datos está aislada.** Hoy leemos CSVs; después será una API. Si el
   parsing está esparcido por los componentes, la migración duele.

Lo demás — framework, librería de mapas, de grafos, de gráficas, estado, estilos —
es tu llamado. Elige lo que tu equipo pueda mantener.

---

## 9. Lo que NO hagas todavía

- **Diseño visual fino.** Primero que la ficha de contrato sea verificable. La
  estética después.
- **Autenticación de usuarios.** Todo es público, no hay cuentas.
- **Infraestructura pesada.** Son 78.000 contratos: caben en un portátil. Nada de
  Kubernetes ni data warehouse en la nube.
- **Machine learning en el front.** Las banderas explicables van primero. Un score
  de caja negra es indefendible ante un editor y ante un juez.
- **Tu propio nombre para las banderas.** Vienen de `banderas_glosario.csv`.

---

## 10. Arranca hoy sin esperarme

**No esperes a que el pipeline termine.** Genera un CSV sintético con
**exactamente** los encabezados de la sección 4 y unas 200 filas inventadas, y
construye encima de eso. Cuando los datos reales lleguen, se cambia el archivo.

Si arrancas sin ese paso, vas a rehacer trabajo.

Incluye en tus datos falsos los casos difíciles a propósito: `ciudad =
'NO DEFINIDO'`, un `urlproceso` con el formato de struct, un contrato con 6 banderas
encendidas, uno con `valor` imposible, un municipio con 4 contratos (para probar que
la tasa ajustada no lo deja encabezar), y nombres en mayúsculas sin tildes con
siglas adentro.

## Definición de terminado

- [ ] Cualquiera puede llegar a un contrato, ver por qué está marcado y verificarlo
      en SECOP II en un clic
- [ ] El mapa ordena por `tasa_ajustada` y muestra también la cruda
- [ ] Las banderas y sus textos salen de `banderas_glosario.csv`, no del código
- [ ] Hay un test que falla si una columna prohibida llega al cliente
- [ ] Ni un solo texto de la interfaz dice "corrupto" o "fraude"
- [ ] La página de metodología lista los falsos positivos conocidos
- [ ] Las cifras se leen como "$209 billones", no como 15 dígitos
- [ ] Las URLs de contrato, municipio y búsqueda son compartibles

Dos cosas que vale la pena que les subrayes al entregarlo: la ficha de contrato es el producto (el mapa es lo vistoso, pero la ficha es lo que hace que un periodista pueda usar esto), y el CSV sintético del día uno — es lo único que les permite trabajar en paralelo sin depender del pipeline.