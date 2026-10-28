# TiresIAs · Segunda ronda: ¿tiene Kronos alguna utilidad? Criterios fijados ANTES de medir (2026-10-28)

La primera ronda ([RESULTADOS.md](RESULTADOS.md)) probó Kronos-small **sin reentrenar**: no predice un valor, su
probabilidad no se cumple, su incertidumbre es estrecha, sus reglas son suerte y no ordena el S&P 500. Pero su propia
demo de trading (`finetune/`) **lo reentrena antes de ordenar valores**, y eso no se probó. Esta ronda tiene una lista
cerrada de cinco hipótesis; no se añaden otras, y si ninguna pasa, se cierra.

## Reglas comunes

- **Periodo**: del 2024-07-01 (fin del preentrenamiento) al 2026-10-23. Las hipótesis que **no eligen ni ajustan nada** con
  datos de ese periodo usan el periodo entero (U1, U2, U4, U5). Las que ajustan (U3) eligen en 2024-07 → 2025-06 y se
  prueban **una vez** en 2025-07 → 2026-10.
- **Varias hipótesis**: corrección de Holm al 5 % sobre el *p* principal de cada una (unilateral). Una hipótesis **pasa** si
  su *p* sobrevive a Holm **y** cumple su criterio económico.
- **Lo que pase** va a la incubadora en sombra (señal registrada antes del resultado) al menos 3 meses antes de usarse.
- **No se hace**: cambiar un criterio, una partición o un parámetro después de ver un resultado; probar variantes no
  listadas; operar con dinero.

## U4 · Reentrenarlo como sus autores (la principal)

Replica `finetune/config.py` y `finetune/qlib_test.py`, cambiando sólo el mercado.

- **Datos**: miembros actuales del S&P 500 (sesgo de supervivencia declarado; U1 no lo tiene), diarios de Yahoo, OHLC +
  volumen + importe (volumen × precio medio). Entrenamiento 2011-01-01 → 2022-12-31; validación 2022-09-01 → 2024-06-30
  (como ellos, con el solape); nada posterior al 2024-06-30 entra en el reentrenamiento.
- **Reentrenamiento**: el tokenizador y luego el predictor, partiendo de las revisiones fijadas; ventanas de 90 + 10 velas,
  30 épocas de 2.000 lotes de 50, AdamW (4e-5 el predictor, 2e-4 el tokenizador; betas 0,9 y 0,95; caída 0,1), OneCycle
  (3 %, divisor 10), recorte 3, semilla 100; el mejor modelo por la pérdida de validación. Un solo proceso (en Windows no
  hay NCCL); si la memoria obliga a un lote menor, acumulación de gradiente hasta 50, y se dice.
- **Señal**: cada sesión, 90 velas, 10 de horizonte, 5 futuros, T 0,6, top-p 0,9; puntuación «last» de su código: el cierre
  previsto a 10 sesiones menos el último, en unidades normalizadas de la ventana.
- **Cartera**: la de su demo, *TopkDropout*: 50 valores, como mucho 5 cambios al día, cada uno al menos 5 sesiones, a la
  apertura, con 0,10 % al comprar y 0,15 % al vender.
- **p principal**: RankIC entre valores de la puntuación con la rentabilidad real de apertura (t+1) a apertura (t+11), en
  fechas cada 10 sesiones (sin solape); *t* de la media.
- **Criterio económico**: exceso neto de la cartera sobre los miembros a partes iguales (reajuste diario sin coste, la vara
  más favorable a la vara) positivo con P ≥ 90 % (bootstrap por bloques de 4 semanas), **y** su Sharpe neto por encima del
  percentil 95 de 200 placebos (las puntuaciones de cada valor barajadas entre fechas).
- **Comparación, sin entrar en Holm**: la misma receta con el modelo sin reentrenar.

## U1 · Ordenar los candidatos del swing

- **Datos**: los candidatos del motor PIT de thalos-ibkr (`precomputar_candidatos`, el camino del WF), cada sesión del
  periodo; sin sesgo de supervivencia. Para cada candidato, la puntuación de U4 (o, si U4 no llega a reentrenarse, la del
  modelo sin reentrenar, y se dice).
- **p principal**: RankIC entre candidatos de la misma sesión (sesiones con ≥ 5) con su rentabilidad de apertura a apertura
  a 5 sesiones, en sesiones cada 5 (sin solape); *t* de la media.
- **Criterio económico**: la mitad de arriba según Kronos rinde más que todos los candidatos, con P ≥ 90 %. Si pasa, antes de
  nada, el walk-forward PIT del motor con ese filtro (regla del proyecto).

## U2 · ¿Sabe algo más que la reversión?

- **Datos**: las predicciones del S&P 500 de la primera ronda (`7396451`).
- **p principal**: RankIC semanal entre valores del **residuo** de su rentabilidad prevista, descontadas (regresión por
  rangos en cada fecha) la última semana y las últimas 20 sesiones, con la rentabilidad real a 5 sesiones; *t* de la media.
- **Criterio económico**: ninguno; es un diagnóstico (si no pasa, U3 y U4 tienen menos de dónde sacar).

## U3 · Una cabeza sencilla sobre su representación interna

- **Características de Kronos**: el estado interno de la última capa en la última vela de cada ventana de 40, sin muestrear.
- **Vara**: ocho características clásicas: rentabilidad a 1, 5, 20 y 60 sesiones, volatilidad de 20, Parkinson de 20,
  volumen de 5 sobre el de 60 y distancia al máximo de 252.
- **Modelo**: ridge sobre el puesto (normalizado en cada fecha) de la rentabilidad a 5 sesiones; el alfa, por validación en
  bloques dentro de 2024-07 → 2025-06; entrenado ahí y probado una vez en 2025-07 → 2026-10.
- **p principal**: diferencia semanal de RankIC entre (Kronos + clásicas) y (sólo clásicas); *t* de la media.
- **Criterio económico**: los 50 primeros de (Kronos + clásicas), reajuste semanal, mejor Sharpe neto que todos con P ≥ 90 %.

## U5 · Bitcoin con el protocolo de cripto de su artículo

- **Datos**: BTC-USD de Yahoo, sólo OHLC (volumen e importe a cero, como su artículo para cripto); 40 velas, T 0,6, top-p
  0,9, 10 futuros, horizonte 5.
- **p principal**: RankIC de la rentabilidad prevista a 5 sesiones con la real, fechas sin solape; *p* por bootstrap de
  bloques de 4 semanas (unilateral).
- **Criterio económico**: la regla de la incubadora E006 (BTC-EUR, dentro si el cierre supera su media de 200) con un veto
  de Kronos **sólo a las entradas** (entra el primer día en que E006 está dentro **y** Kronos da más de 0,5 de
  probabilidad de subida; las salidas, las de E006) mejora el Sharpe neto de E006 sola, con 1,49 % por operación, con
  P ≥ 90 %. Potencia baja, dicha antes: un activo, pocas transiciones de E006.
