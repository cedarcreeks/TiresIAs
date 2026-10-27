# TiresIAs · Plan y criterios, fijados ANTES de medir (2026-10-27)

TiresIAs es un fork de [Kronos](https://github.com/shiyu-coder/Kronos) (MIT) para contestar una pregunta concreta:
**¿predice Kronos algo útil en estos valores, después de la fecha de corte de su entrenamiento y con costes?**
Y, si tiene puntos flacos, pulirlos con el mismo rigor. Este documento se publica antes de calcular ningún
resultado: el historial de git fecha cada criterio.

## Por qué sólo desde julio de 2024

Kronos se preentrenó con datos **hasta junio de 2024** (artículo, arXiv 2508.02739). Todo lo anterior el modelo lo ha
visto. Periodo de evaluación: **del 2024-07-01 al 2026-10-23** (última sesión cerrada en todas las descargas usadas).

## Configuración principal (la del artículo, no elegida aquí)

Kronos-small (revisión de Hugging Face fijada, la de los tests de upstream), 40 velas diarias de historia,
temperatura 0,6, *top-p* 0,9, **N = 10 trayectorias**. De ellas, en cada fecha *t*:
- **rentabilidad prevista**: la media de las trayectorias en *t+H* frente al cierre de *t*;
- **probabilidad de subida**: la fracción de trayectorias que acaban por encima del cierre de *t*.

Semilla fija por (valor, lote); cada experimento corre entero en un dispositivo, que se apunta.

## Prueba principal: 5 valores

Indra (`IDR.MC`), ACS (`ACS.MC`), `SPY`, `3USL.MI` y bitcoin (`BTC-EUR`). Datos diarios de Yahoo (OHLC ajustados por
splits como entrada; rentabilidad total, con dividendos, para medir lo ganado).

Dos horizontes, como se operaría a mano:
- **diario (H = 1)**: tras el cierre de *t*, dentro si la probabilidad de subida pasa de 0,5; se compra o vende a la
  apertura de *t+1* y se mantiene hasta la apertura siguiente;
- **semanal (H = 5)**: lo mismo cada 5 sesiones, sin solape.

Costes por operación: **0,25 % en acciones y ETF y 1,49 % en bitcoin** (Revolut, a verificar en la app). Cada
resultado lleva su **coste de equilibrio**, el coste por operación con el que la estrategia iguala a comprar y mantener.

**Kronos aporta en un horizonte sólo si, a la vez:**
1. la media de las RankIC de los 5 valores (correlación de rangos entre rentabilidad prevista y real) es > 0 con el
   intervalo del 90 % (bootstrap de bloques) entero por encima de 0;
2. la cartera a partes iguales de las 5 estrategias, **neta de costes**, tiene mejor Sharpe que comprar y mantener
   los 5 **y** que la mejor de las reglas ingenuas (seguir la última semana; la media de 200 sesiones), con
   P(ΔSharpe > 0) ≥ 90 % (bootstrap estacionario, bloques de 20 sesiones);
3. supera al **placebo**: su Sharpe neto cae por encima del percentil 95 de 1.000 placebos (las mismas señales
   barajadas entre fechas, dentro de cada valor);
4. no depende de uno solo: al menos 3 de los 5 valores con RankIC > 0.

Si no pasa, se dice con su cifra. Lo exploratorio (H = 12, otros umbrales, otros tamaños de modelo) se dice como tal.

## Prueba secundaria: el S&P 500

La de su artículo: ranking entre valores. Cada 5 sesiones, rentabilidad prevista a 5 días de cada valor; cartera de
los 50 primeros a partes iguales frente a todos a partes iguales, con 0,10 % por operación. Pasa si la RankIC
transversal media es > 0 con *t* > 2 y la cartera de los 50 cumple los puntos 2 y 3 frente a la de todos. **Sesgo
declarado**: los valores son los miembros actuales del índice; los que salieron entre 2024 y 2026 no están (Yahoo no
guarda los retirados), y eso favorece a cualquier estrategia larga.

## El pulido (fase 4)

Desarrollo: 2024-07 → 2025-06. Prueba final: 2025-07 → 2026-10, **una vez** por mejora, con estos mismos criterios.
Una mejora que sólo gana en el desarrollo es ruido.

## Lo que no se hace

*Fine-tuning* con el periodo de prueba; buscar la configuración que mejor salga; operar con dinero real.
