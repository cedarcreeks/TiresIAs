# Resultados de la segunda ronda: ¿tiene Kronos alguna utilidad? (2026-10-29)

Criterios fijados antes de medir en [PLAN_UTILIDAD.md](PLAN_UTILIDAD.md) (`9b79c32`; la concreción de las sesiones de
U1, `2d01b85`, y la desviación del lote de U4, `ac29a3f`, escritas antes de ver sus resultados). Periodo: 2024-07-01 →
2026-10-23. Aquí sólo hay agregados: ningún precio.

**Veredicto: ninguna de las cinco pasa. Como dice el plan, la línea se cierra.**

**Estado (29-oct): aparcado.** No se prueban más configuraciones; si se retoma, con una declaración nueva y a futuro (el periodo posterior al preentrenamiento ya está usado).

| | qué mide | *p* principal | sobrevive a Holm | criterio económico | pasa |
|---|---|---|---|---|---|
| U1 | ordena los candidatos del swing (RankIC por sesión, 26 sesiones) | 0,105 | no | no: la mitad de arriba gana con P 0,62 (pide ≥ 0,90) | no |
| U2 | sabe algo más que la reversión de la última semana | 0,418 | no | — (diagnóstico) | no |
| U3 | su estado interno añade a ocho características clásicas | 0,714 | no | no: Sharpe 1,42 frente a 1,76, P 0,26 | no |
| U4 | **reentrenado como sus autores**, su receta de trading en el S&P 500 | 0,790 | no | no: P(exceso > 0) 0,06; Sharpe 0,84 bajo el placebo p95 1,25 | no |
| U5 | bitcoin con su protocolo de cripto, veto a E006 | 0,828 | no | no: P 0,71 | no |

Holm al 5 % sobre cinco: el *p* más pequeño tendría que ser ≤ 0,01; el más pequeño es 0,105.

## U4, la principal: reentrenarlo como sus autores

Su `finetune/` cambiando sólo el mercado: tokenizador y predictor reentrenados con el S&P 500 de 2011 a 2022 (validación
hasta 2024-06-30), puntuación «last» de su `qlib_test.py` y su cartera *TopkDropout* de Qlib (50 valores, ≤ 5 cambios al
día, ≥ 5 sesiones, 0,10 % al comprar y 0,15 % al vender).

| | reentrenado | original (comparación) | todos a partes iguales |
|---|---|---|---|
| RankIC medio, 58 fechas sin solape | −0,0072 (*t* −0,81) | +0,0086 (*t* +0,46) | |
| Sharpe neto de la cartera | 0,84 | 1,18 | 1,29 |
| CAGR neto | 12,7 % | 21,4 % | 19,9 % |
| rotación anual | 39 | 17 | |
| placebo, p50 / p95 | 0,93 / 1,25 | 1,01 / 1,28 | |

El original se predijo cada 10 sesiones (coste de la GPU), así que su cartera opera 10 veces menos y la comparación de
carteras no es en igualdad. **Exploratorio**: el reentrenado sólo en esas mismas fechas da Sharpe 1,44 (CAGR 23,6 %),
pero **sus mismas puntuaciones barajadas entre fechas dan más**: placebo p50 1,56, p95 1,82. Lo que rinde es una
inclinación fija por valor, no la señal de cada día; y como los valores son los miembros actuales del índice (sesgo de
supervivencia declarado), esa inclinación puede venir de ahí. No se ha medido.

### ¿Se reentrenó bien?

- **Los pesos son los que se entrenaron**: con los guardados se reproduce en otra máquina la pérdida de validación
  apuntada al entrenar (diferencia 2e-7).
- **Aprendió estos datos**: frente al original, en la misma validación, el tokenizador reconstruye un 31,5 % mejor y el
  predictor baja su pérdida un 0,7 %.
- **Se usó el modelo reentrenado**: sus puntuaciones difieren de las del original en las 29.408 que tienen en común (ninguna igual);
  correlación mediana por valor, 0,10.
- **En su propia métrica** (apéndice D de su artículo: la correlación, en cada predicción, entre el camino previsto y el
  real de cada canal de precio; 100 valores, fechas de 10 en 10, la misma semilla para los dos): IC 0,022 frente a
  0,013 del original, RankIC 0,022 frente a 0,013. La diferencia, +0,009, **no se distingue del azar** (*t* 0,57 con
  las 58 fechas como unidad, *p* 0,28). Es el orden de lo que su artículo publica para Kronos-small (RankIC 0,0254,
  con 40 velas, 12 de horizonte y 10 futuros). El reentreno no la empeoró; si la mejora, con estos datos no se ve.
- **Desviación declarada**: su lote es por GPU y sus scripts se lanzan en varias (su ejemplo, 2); con una, el lote
  efectivo fue 50 y no 100.

## Verificación

- **Segunda implementación de U4** (`tiresias/verificar_u4.py`): lee por fecha con pandas y traduce línea a línea
  `TopkDropoutStrategy` de Qlib. Las nueve cifras de U4 (RankIC, *t*, *p*, *n*, Sharpe, CAGR, rotación y la vara)
  coinciden en los dos modelos con diferencias ≤ 1e-14; su test caza dos mutantes de `u4.py` (el RankIC con un día de
  desfase y la cartera con la señal del mismo día). Con las dos convenciones exactas de Qlib (repartir el efectivo
  también entre los que no cotizan; la comisión sobre lo comprado) el CAGR cambia menos de 0,02 pp.
- **Segunda implementación de U1**: otro camino para la rentabilidad, los rangos y la selección sin solape; mismas 26
  sesiones, mismo RankIC y mismo exceso.
- **Datos**: las predicciones viajaron del PC con GPU con su SHA-256; las velas que usó son un subconjunto exacto de las
  del Mac (500 ficheros, 0 diferencias).

## Dónde queda flojo

- **Sesgo de supervivencia** en U1 y U4: Yahoo no guarda los valores retirados. Favorece a cualquier estrategia larga;
  no cambia un veredicto negativo.
- **Potencia baja en U1**: 26 sesiones con ≥ 5 candidatos (mediana 7). Un RankIC de +0,12 con *t* 1,29 no distingue
  nada; tampoco lo descarta.
- Sólo Kronos-small; 2,3 años casi todos alcistas; un solo reentrenamiento (otra semilla daría otro modelo).
- **U4 con lote 50 y no 100**: declarado antes de ver resultados; el mejor predictor salió en la época 4 de 30 y después
  empeoraba, lo que no apunta a falta de pasos.

## Reproducir

```bash
python -m tiresias.u4 evaluar --dir <velas> --pred <pred_reentrenado>
python -m tiresias.verificar_u4 --dir <velas> --pred <pred_reentrenado>
python -m tiresias.u4 comparar --dir <velas> --reentrenado <pred_reentrenado> --original <pred_original_10> --salida comparar.json
python -m tiresias.u4 camino --dir <velas> --u4 <modelos> --valores 100
python -m tiresias.u1 puntuar --dir <ronda2/u1> --u4 <modelos> && python -m tiresias.u1 evaluar --dir <ronda2/u1>
python -m tiresias.ronda2 veredicto --u1 u1.json --u2 u2.json --u3 u3.json --u4 u4.json --u5 u5.json
```
