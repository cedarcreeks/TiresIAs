# TiresIAs · Fase 2B · Resultados

Plan y criterios: [PLAN_FASE2.md](PLAN_FASE2.md), apartado 2B, fijados antes de bajar los datos.

## Veredicto: NO (1 de 4) — la receta de los mejores gestores 13F no bate al S&P 500

Se eligió el decil superior de gestores por la t de su alfa a 36 meses, sin mirar al futuro, y se aplicó su receta de
factores (la construcción de 2A′). Juicio de 2019-04 a 2026-08 (89 meses), neto del 0,5 % anual de coste:

| | Sharpe | CAGR |
|---|---|---|
| Receta del decil superior | 0,794 | 15,6 % |
| S&P 500 con dividendos | 0,831 | 16,2 % |
| Receta de todos los gestores | 0,767 | 14,3 % |
| Placebo (decil al azar, 200 veces), mediana / p95 | 0,767 / 0,792 | — |

| Criterio | | |
|---|---|---|
| 1 · Sharpe +0,10 y CAGR +1 pp frente al S&P 500 | −0,04 y −0,6 pp | **no** |
| 2 · Lo mismo en las dos mitades | — | **no** |
| 3 · Por encima del p95 del placebo | 0,794 frente a 0,792 | sí, por un pelo |
| 4 · +0,05 de Sharpe sobre «todos los gestores» | +0,027 | **no** |

**Robusteces.** El criterio 3 no aguanta: con cobertura mínima del 80 %, 0,752 frente a 0,758; con el 95 %, 0,800
frente a 0,848. Con la cota pesimista de las salidas de bolsa, el resultado es el mismo que el principal (1 de 4).
Ninguna variante bate al S&P 500.

**Control positivo, para saber que la maquinaria ve la habilidad cuando la hay.** Si se elige con un oráculo (los
gestores con mejor rentabilidad real el trimestre siguiente), copiar sus carteras da Sharpe 2,28 y CAGR 53,8 %; un decil
al azar, 0,70 y 13,3 %. El «no» no es un fallo del montaje.

**Comparaciones del plan (informativas, sin criterio).**

| | Sharpe | CAGR |
|---|---|---|
| Copiar las cinco mayores posiciones de cada elegido | 0,891 | 18,1 % |
| ETF GURU real | 0,532 | 11,7 % |

Copiar las mejores ideas de los elegidos queda por encima del S&P 500 (+0,06 de Sharpe, +1,9 pp de CAGR). No se probó
con placebo ni por mitades, y queda por debajo de la vara de +0,10 que se exigió a la receta. Es una **hipótesis para
un plan nuevo**, no un resultado.

**Los datos del juicio.**

- La cobertura agregada con precio, por trimestre, va del 88,6 % al 99 %, con mediana 95,4 %: la regla de parada no
  salta.
- Los CUSIP con traducción comprobada con el precio del FTD son 21.221; otros 8.963 «no cuadran» o no existen en
  Alpaca (OTC, extranjeros); su peso en valor ya está en la cobertura.
- Los corporate actions de Alpaca coinciden con la traducción de los FTD en el 99,5 % de 236.641 comparaciones; los
  881 CUSIP que discrepan quedan fuera.
- Se eligen entre 102 y 372 gestores por decisión, con mediana 230.

**Lo que no funcionó, mío** (todo cazado antes de dar cifras):

- la revisión pedía el margen dos veces y habría repetido la descarga entera;
- `acciones_de` era de orden CUSIP × eventos: más de 51 minutos sin acabar, frente a 1 minuto con el índice;
- un símbolo vacío iba al pedido;
- el «trimestre anterior» de 3C caía en el mismo trimestre.

**Dónde queda flojo.**

- Los *spin-offs* y fusiones de antes de 2020 que Alpaca no registra quedan sin corregir.
- Los factores de AQR acaban en 2026-08 y fijan el final del juicio.
- La receta es una construcción con factores en largo y corto, antes de impuestos: aunque hubiera pasado, faltaría 2C.


## Los datos: 13F y FTD (31-oct-2026)

**De dónde vienen.** La SEC respondió 403 («Request Rate Threshold Exceeded») a los programas desde la IP de la casa
durante toda la jornada, aunque a un navegador le cargaba. No se intentó esquivar. Los ficheros salieron de la copia
del Internet Archive, que guarda los mismos zips con su URL original:

- **13F**: 42 conjuntos, de 2016q1 a la ventana de mar–may-2026. No está la ventana de jun–ago-2026.
- **FTD**: 246 de los 260 quincenales de dic-2015 a sep-2026. Los que faltan son abr–jun-2017, feb–abr-2020 y tres
  quincenas de 2026; ningún hueco pasa de 3 meses y la traducción usa el registro anterior más cercano. Los de 2016–17
  estaban en una ruta antigua (`sec.gov/foia/failsreports/`), que salió de una copia archivada de la página de la SEC.

**Cómo se verificó.**

- **Archivo**: cada fichero, contra el SHA-1 del índice del archivo y con el CRC de su zip; los 288, bien.
- **SEC directa**: cuatro ficheros bajados de la SEC desde el navegador. Tres son idénticos byte a byte.
  `2016q1_form13f.zip` no lo es, porque **la SEC regeneró los trimestrales el 15-feb-2024**: añadió la columna FIGI y 3
  presentaciones de 4.184 (177 posiciones de 1.023.199). Las posiciones comunes coinciden todas en valor. Las 30 copias
  trimestrales del archivo son de antes de esa regeneración; cuando hay copia de la SEC, manda la de la SEC.
- **Lectura**: las filas de cada FTD cuadran con su recuento final en los 246 ficheros, porque la lectura falla si no.
  Cada línea de las tablas de 13F tiene los campos de su cabecera.

**Lo que queda**: 63,5 M de posiciones de 12.470 gestores en 77.925 CUSIP. Son sólo 13F-HR originales, acciones (`SH`)
y sin opciones. Un 13F atrasado de un periodo anterior al último presentado no cuenta.

**La traducción CUSIP → símbolo con fecha** cubre del 98,3 % al 99,9 % del valor de cada uno de los 42 trimestres. Es
una cota superior: luego hace falta el precio.

- **Contraste con el precio**: el `PRICE` de cada registro FTD es, según la SEC, el cierre del día anterior. Coincide
  con el cierre sin ajustar de Alpaca, con mediana y p99 de |Δ| de 0,000 % en 13.529 registros de 27 valores conocidos.
  Por eso cada tramo (CUSIP, símbolo) se da por bueno sólo si su mediana de |Δ| es ≤ 1 %.
- **Clases**: el FTD las escribe sin punto (BRKB por BRK.B). La forma con punto sólo se toma si cuadra con el precio,
  porque BRKL y BRKR son otras empresas.
- **Avance** con 95 de los 590 lotes de la primera pasada: el 98,29 % del valor evaluable cuadra con su precio, el
  1,71 % espera la forma con punto y ninguno «no cuadra».

**Una hipótesis de la descarga, comprobada**: un lote con `asof=-` no se calla ningún símbolo. De 200 «sin datos»
elegidos al azar y pedidos uno a uno, ninguno trajo barras. Por eso en los otros modos sólo se repiten solos los
símbolos que sí tienen barras tal como cotizaron.

## Los precios: validación de `tiresias/precios.py` (31-oct-2026)

Antes de bajar ningún precio de 2B se validó el módulo con 27 valores de 2016-01 a 2026-09: AAPL, EW, ISRG, NVDA, TSLA,
GOOGL, AMZN, WMT, CMG, AVGO (*splits*); GE, JNJ, MMM, T, IBM, PFE (*spin-offs*); KO, XOM, MSFT, JPM, DIS, META, BRK.B,
HD, PG, UNH, V. La referencia es la rentabilidad mensual de Yahoo (cierre ajustado). Para los *spin-offs*, la verdad se
calcula aparte: el día *ex*, el precio sin ajustar más lo escindido a su cierre de ese día. Los datos no están en el
repositorio; el guion está en `exploratorio/validar_precios_2b.py`.

| | meses-valor | mediana de \|Δ\| | meses con \|Δ\| > 1 pp |
|---|---|---|---|
| Camino de Alpaca (la entidad coincide), fuera de meses con *spin-off* | 3.449 | 0,0025 pp | 0 |
| Camino reconstruido, forzado en los 27 (precio sin ajustar + *corporate actions*) | 3.449 | 0,0000 pp | 0 |

META entra como FB hasta el 8-jun-2022 y como META desde el 9, en dos tramos unidos. Los 27 van por el camino de
Alpaca: la comprobación de entidad pasa en todos.

*Spin-offs*, rentabilidad del mes en %:

| | módulo | verdad | Alpaca sin corregir | Yahoo |
|---|---|---|---|---|
| PFE / VTRS, 2020-11 | 15,19 | 15,19 | 9,06 | 14,98 |
| T / WBD, 2022-04 | 5,72 | 5,72 | 6,04 | 7,20 |
| GE / GEHC, 2023-01 | 23,65 | 23,65 | 23,41 | 23,04 |
| GE / GEV, 2024-04 | 16,04 | 16,04 | 15,80 | 15,72 |
| MMM / SOLV, 2024-04 | 7,70 | 7,70 | 13,44 | 8,82 |
| GE / WAB, 2019-02 | 6,23 | 6,23 | 6,40 | 6,35 |
| IBM / KD, 2021-11 | **−5,15** | −1,01 | −5,15 | −0,78 |

IBM/KD no está en los *corporate actions* de Alpaca y queda sin corregir: es el caso que el módulo no puede ver. Su
efecto en una cartera es su peso por la diferencia: con un 2 % de peso, 0,08 pp ese mes.

**Controles negativos.** Con barras reales, un tramo del CUSIP del ETF de Roundhill que se salta su paso a METV sale
«descartada»: el guardián ve el salto de 12,31 a 184 sin evento que lo explique. El primer mes de los datos de Alpaca
(enero de 2016, sin el cierre de diciembre) salía hasta 6,5 pp lejos de Yahoo en 17 valores. Lo destapó esta
validación, y desde entonces un mes sin cierre del mes anterior no cuenta. 27 mutantes del módulo, todos mueren.

**Una trampa más de Alpaca, cazada al repetir la descarga con el código del repositorio**: en una petición de varios
símbolos, los traduce a su empresa de hoy y quita los repetidos **sin avisar** (FB y META juntos devuelven sólo
META; SQ y XYZ, sólo XYZ). La primera repetición perdió FB y mandó META al camino reconstruido. Desde entonces, cada
símbolo que un lote no devuelve se pide solo, y lo que siga sin nada se cuenta (`Alpaca.sin_datos`): en esta muestra,
ninguno.

**Dónde queda flojo.**
- Los *spin-offs* sin registro en Alpaca (IBM/KD) quedan sin corregir.
- Las fusiones de antes de ~2022 no están en los *corporate actions*: la salida se mide hasta el último cierre, sin el
  pago final. En una fusión en efectivo, la diferencia es el diferencial de la operación, normalmente por debajo del 1 %.
- Las quiebras se miden hasta el último cierre en bolsa. Por eso existe la cota pesimista de la robustez.
