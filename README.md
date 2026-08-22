# Plomada

> La plomada es el instrumento que revela lo que está torcido.

Detección de riesgo de irregularidad en la **contratación de obra pública** de
Colombia, a partir de datos 100% públicos del SECOP II.

**Riesgo no es fraude.** Este proyecto produce indicios para priorizar
investigación periodística y control social. Ninguna cifra de aquí prueba un
delito, y el proyecto no afirma que lo pruebe.

---

## Qué lo diferencia de un buscador de contratos

Las herramientas existentes (BuscaSECOP y similares) son **buscadores de filas**:
filtras por entidad, objeto, cuantía y modalidad. Plomada trata los contratos
como **aristas de una red de personas** y se enfoca en un solo sector —
construcción — porque es el único donde puedes verificar físicamente si la obra
existe.

Los campos que habilitan esto están en el dataset oficial y casi nadie los usa:

| Campo del SECOP II | Para qué sirve |
|---|---|
| `n_mero_de_documento_ordenador_del_gasto` | Cédula del funcionario que autorizó el gasto. Se lo puede seguir cuando cambia de entidad. |
| `n_mero_de_documento_supervisor` | Quién vigila la obra. |
| `identificaci_n_representante_legal` | Empresas que comparten representante legal. |
| `n_mero_de_cuenta` | Proveedores distintos cobrando a la misma cuenta. **Nunca se publica**: se usa como llave hasheada. |
| `direcci_n_de_ejecuci_n_del_contrato` | Geocodificable → verificación satelital de la obra. |
| `sistema_general_de_regal_as` y afines | Atribuir el riesgo a la fuente de la plata. |

## Universo

De los **5.975.627** contratos del SECOP II, 5.123.891 son prestación de
servicios. El universo de obra pública son **77.864** contratos, **$209
billones**:

| Tipo | Contratos |
|---|---|
| Obra | 52.355 |
| Interventoría | 13.074 |
| Consultoría | 11.482 |
| Asociación Público Privada | 715 |
| Concesión | 238 |

Interventoría y consultoría se incluyen **a propósito**: que el que vigila la
obra pertenezca a la misma red que el que la construye es el mecanismo central
del fraude en obra pública, y solo se ve si tienes los dos lados.

## Cómo correrlo

```bash
pip install duckdb requests
python src/ingest.py    # ~4 min, descarga a data/raw/ (reanudable)
python src/build.py     # ~20 s, arma data/warehouse/plomada.duckdb
python src/report.py    # reportes por consola + CSVs en out/
```

## Decisiones metodológicas (verificadas contra los datos, no supuestas)

Estas son las trampas en las que cae cualquier port ingenuo de las "banderas
rojas" de la literatura al caso colombiano. Todas se descubrieron midiendo.

**1. La API oficial no sirve para analizar.** Las agregaciones (`$group`) sobre
los 6M de contratos se caen por timeout. Una página cruda de 10.000 filas baja
en ~30 s sin problema. Por eso se traen las filas a disco y toda la analítica
corre en local con DuckDB.

**2. Las llaves nativas contrato↔proceso no cruzan.** El dataset de contratos
usa el namespace `CO1.BDOS.*` y el de procesos `CO1.REQ.*`; el match exacto da
**cero**. El único puente común es el `noticeUID=CO1.NTC.*` que va dentro de la
URL pública de ambos. Con eso el join sube a **99,6%** de cobertura, y es lo que
habilita las banderas de competencia.

**3. El dataset de procesos trae varias filas por proceso** (una por lote y por
adjudicación). Unir directo duplica contratos y contamina todos los conteos. Se
colapsa a una fila por proceso *antes* de unir.

**4. 24 contratos traen valores imposibles** (hasta 6×10¹⁸ COP, más que el PIB
mundial) y entre ellos concentraban el **98,6% del "total"** agregado. No se
borran: se aíslan, se cuentan como falla de publicación (`f_valor_implausible`)
y se excluyen de toda suma de dinero.

**5. Buscar anticipos por encima del 50% legal es inútil.** El máximo observado
en los 1.590 contratos con anticipo es exactamente **0,500**: la plataforma
impone el tope. Esa bandera clásica no puede dispararse nunca. Lo que sí informa
es quién **agota** el tope (589 contratos), y los 271 que declaran *no* tener
anticipo pero registran plata girada.

**6. "Pagado mucho con ejecución pendiente" es imposible por construcción.**
`valor_pagado + valor_pend_ejecucion = valor` se cumple en 72.110 de 76.576
contratos (94%): es una identidad contable, no una señal. Se reemplazó por las
**violaciones** de esa identidad, que sí son anomalías (9 sobrepagos).

**7. No toda cuenta bancaria compartida es un indicio.** Se clasifica el tipo de
red antes de usarla:
   - *comunitaria* (4 grupos): el municipio canaliza pagos a varias Juntas de
     Acción Comunal por una misma cuenta. Ruido administrativo. **Se excluye.**
   - *consorcios* (63 grupos): la cuenta del consorcio suele estar a nombre del
     líder. Esperable; se marca aparte con menor fuerza probatoria.
   - *empresas independientes* (30 grupos): **este es el indicio real.**

   Sin esta separación, la bandera reportaría 651 contratos; con ella, 239.

**8. Cuando el Estado le contrata al Estado, la directa es legal.** Los
convenios interadministrativos (ANI→INVIAS, empresas industriales y comerciales
del Estado, ESEs) usan contratación directa por vía legal. Filtrando los 783
proveedores que son entidades públicas, `f_obra_directa` baja de 12.154 a
**8.944**: el **26% eran falsos positivos**.

**9. Los municipios chicos no pueden encabezar el ranking por azar.** Un
municipio con 4 contratos y 2 marcados da 50% y gana la lista sin significar
nada. Se corrige con **encogimiento bayesiano empírico** (beta-binomial por
momentos): las tasas con poca evidencia se jalan hacia la media nacional y solo
se separan cuando hay volumen que lo sostenga. Se reportan la tasa cruda y la
ajustada, siempre las dos.

## Las banderas

20 indicadores en 6 grupos, con pesos explícitos y discutibles (3 = indicio
fuerte, 1 = contexto). El glosario completo y sus pesos están en
`out/banderas_glosario.csv` y en `sql/03_ranking.sql`. Cada contrato marcado
lleva las columnas `ev_*` con la evidencia numérica que disparó cada bandera:
sin evidencia no se publica.

Un contrato cuenta como **atípico** si enciende al menos una bandera fuerte o
acumula 6 puntos. Umbral explícito, no escondido en un modelo.

## Limitaciones que hay que decir en voz alta

- **Solo SECOP II.** SECOP I (pre-2015 y entidades rezagadas) no está incluido.
- **La cédula del ordenador del gasto está en el 64,5%** de los contratos y la
  del supervisor en el 54,3%. El análisis de red cubre esa fracción, no el total.
- **La cuenta bancaria está en el 23,7%.** Las redes detectadas son un piso, no
  un censo.
- **No hay datos de oferentes perdedores** en los datos abiertos, solo el número
  de ofertas y el ganador. Eso limita la detección de colusión a indicios
  indirectos: no se puede ver quién compitió contra quién.
- **Falta normalizar por población** (DANE) para el ranking municipal.
- **Falta la línea de precios unitarios**, que es lo que convertiría el riesgo en
  una cifra de sobrecosto en pesos.

## Pendiente

1. Precios unitarios de construcción → sobrecosto estimado en pesos.
2. Grafo completo con detección de comunidades (Louvain) y captura de
   interventoría: interventor y constructor en el mismo clúster.
3. Verificación satelital (Sentinel-1/2) sobre `direcci_n_de_ejecuci_n_del_contrato`,
   validada contra el Registro Nacional de Obras Civiles Inconclusas.
4. Alertas **pre-adjudicación** sobre procesos abiertos, para que la observación
   al pliego se pueda radicar mientras el término sigue corriendo.

## Fuentes

- SECOP II – Contratos Electrónicos: `jbjy-vk9h` en datos.gov.co
- SECOP II – Procesos de Contratación: `p6dx-8zbt` en datos.gov.co
- Antecedente académico: *VigIA: prioritizing public procurement oversight with
  machine learning models and risk indices*, Data & Policy (Cambridge, 2024).
  Sus autores señalan como trabajo pendiente justamente el análisis de red de
  proveedores con métodos de grafos.

## Licencia

Código y metodología abiertos. Los datos son públicos y de propiedad del Estado
colombiano.
