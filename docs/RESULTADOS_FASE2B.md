# TiresIAs · Fase 2B · Resultados (en curso)

Plan y criterios: [PLAN_FASE2.md](PLAN_FASE2.md), apartado 2B, fijados antes de bajar los datos.

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
