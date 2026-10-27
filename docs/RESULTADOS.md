# Resultados de la F2: Kronos-small sobre 5 valores (2026-10-27)

Criterios fijados antes de medir en [PLAN.md](PLAN.md) (`8f665d0`). Predicciones con `d93ac0e` en CPU; datos diarios de Yahoo descargados el 2026-10-27, del 2024-07-01 al 2026-10-23, 10 trayectorias por fecha, 40 velas de historia. Aquí sólo hay agregados: ningún precio.

**Veredicto: Kronos no aporta en ningún horizonte.**

| | RankIC media (IC 90 %) | Sharpe cartera Kronos | mantener | mejor ingenua | P(mejor que mantener) | placebo p95 | criterios cumplidos |
|---|---|---|---|---|---|---|---|
| diario (H = 1) | +0,020 (−0,006 a +0,046) | −0,84 | 1,44 | 1,42 (media de 200) | 0,00 | −0,76 | 1 de 4 (el 4.º) |
| semanal (H = 5) | +0,022 (−0,039 a +0,090) | 0,54 | 1,46 | 1,41 (media de 200) | 0,01 | 1,08 | 0 de 4 |

Criterios: 1, RankIC media por encima de 0 con su intervalo; 2, Sharpe neto mejor que mantener y que la mejor regla ingenua, con P ≥ 90 %; 3, por encima del percentil 95 del placebo; 4, al menos 3 de 5 valores con RankIC > 0.

A 12 sesiones (exploratorio): RankIC media +0,039 (−0,080 a +0,172).

## Por valor

| valor | RankIC 1 / 5 / 12 | cobertura 10–90 a 5 (debería ser 80 %) | CAGR Kronos semanal | mantener | operaciones/año | coste de equilibrio |
|---|---|---|---|---|---|---|
| IDR.MC | +0,047 / −0,046 / +0,102 | 30 % | +9,4 % | +67,4 % | 23 | ni gratis |
| ACS.MC | +0,030 / +0,187 / +0,228 | 33 % | +37,3 % | +48,3 % | 24 | ni gratis |
| SPY | +0,050 / +0,087 / +0,140 | 29 % | +6,3 % | +16,8 % | 23 | ni gratis |
| 3USL.MI | −0,012 / −0,016 / −0,113 | 33 % | +11,0 % | +28,9 % | 25 | ni gratis |
| BTC-EUR | −0,016 / −0,103 / −0,162 | 33 % | −47,4 % | +8,6 % | 28 | ni gratis |

Costes por operación: 0,25 % en acciones y ETF y 1,49 % en bitcoin. Rentabilidad de apertura a apertura, con dividendos; «coste de equilibrio», el coste con el que Kronos igualaría a mantener (ni gratis: ni sin costes).

**Lo más claro**: su banda del percentil 10 al 90 contiene lo real muy por debajo del 80 % nominal; Kronos dibuja futuros demasiado parecidos entre sí. Es lo primero que tratará de pulir la fase 4.

**A su favor, y aun así no pasa**: en las acciones españolas, ~6–8 % de las aperturas de Yahoo son idénticas al cierre anterior; si son rellenos, la simulación le regala el salto de la noche esos días.

## Reproducir

```bash
python -m tiresias.correr --simbolos IDR.MC ACS.MC SPY 3USL.MI BTC-EUR --H 1 5 12 --fin 2026-10-23 --dispositivo cpu --salida <dir>
python -m tiresias.informe --dir <dir> --salida <dir>/veredicto.json
python -m tiresias.resultados --dir <dir> --salida docs/RESULTADOS.md
```

Con otro día de descarga, Yahoo puede haber revisado algún dato; con otro dispositivo, el azar del muestreo cambia (la semilla fija sólo reproduce en el mismo). Cada predicción guarda su procedencia.
