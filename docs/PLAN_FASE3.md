# TiresIAs · Fase 3 · Seguir a quien le va bien ahora — plan y criterios, fijados ANTES de medir (2026-10-31)

Este documento se publica antes de bajar ningún dato de la fase 3: el historial de git fecha cada criterio.

## La pregunta

**¿A quien le va bien ahora le seguirá yendo bien, y se puede imitar lo que hace?** Dos poblaciones con historial
público: traders de Hyperliquid (cada operación y la curva de patrimonio de cada cuenta son públicas) y congresistas de
EE. UU. (sus operaciones se declaran por ley, con retraso).

**Por qué no REA.** [REA](https://github.com/morluto/rea) hace ingeniería inversa de programas distribuidos (binarios,
apps, webs, contratos EVM) y su aviso legal excluye copiar software propietario. Un historial de operaciones es una
tabla, no un programa: imitar una estrategia desde sus operaciones es un problema estadístico, y se trata como tal.

**Lo que ya se sabe (medido el 31-oct, antes de este plan).** NANC, el ETF que copia las operaciones declaradas de los
congresistas demócratas, de feb-2023 a oct-2026: +20,3 %/año frente a +18,9 % del SPY, beta 1,08, **alfa 0,0 %/año**,
Sharpe 1,19 frente a 1,25. Copiar en bloque no aporta; la pregunta que queda es si elegir **a quién** copiar sí.

## 3A · Hyperliquid: ¿persiste el resultado? (el techo, antes de ningún modelo)

Si los buenos de una ventana no siguen siéndolo en la siguiente, ningún clon puede hacerlo mejor: la línea se cierra
sin construir modelos.

- **Datos**: la clasificación pública (48.222 cuentas el 31-oct) y la curva de patrimonio y resultado de cada cuenta
  (`portfolio`, desde su inicio). Universo: cuentas con patrimonio ≥ 10.000 $ al inicio de A y actividad en A y en B.
- **Muestra** (fijada el 31-oct antes de bajar ninguna curva): 6.000 cuentas al azar, uniformes, de la clasificación
  del 31-oct, con semilla 31. La API admite 1.200 de peso por minuto e IP; el peso de `portfolio` no está documentado y
  se pide a una consulta por segundo, así que las 48.222 serían ~13 h y la muestra ~100 min. El universo de arriba se
  filtra **sobre la muestra**, nunca por el resultado.
- **Ventanas**: A = 2025-11-01 → 2026-04-30 y B = 2026-05-01 → 2026-10-30 (seis meses cada una).
- **Medida**: la rentabilidad de cada cuenta en cada ventana, su resultado dividido entre el patrimonio medio, para
  que las aportaciones y retiradas no cuenten como rentabilidad.
- **Pasa sólo si se cumplen las dos**: (1) correlación de rangos de Spearman entre A y B positiva con p < 0,01
  (unilateral, por permutación con 10.000 barajados); (2) la mediana en B del decil superior de A por encima del percentil 95 de un placebo (deciles elegidos
  al azar, 200 repeticiones).
- **Sesgo declarado**: la clasificación sólo lista las cuentas que existen hoy. Las que se arruinaron y se fueron
  pueden faltar, y eso favorece la persistencia. Un «no» es por tanto fuerte; un «sí», más débil.

## 3B · Hyperliquid: el clon (sólo si 3A pasa)

Imitar a los que persisten y operan con baja frecuencia (sus 10.000 operaciones públicas cubren meses):

- un modelo interpretable de la dirección de su posición en BTC y ETH, a partir de variables de mercado de ese momento
  (tendencia, volatilidad, financiación);
- entrenado en A y probado en B frente al placebo (clones de cuentas al azar) y frente a mantener;
- **restringido a largo/fuera en contado**, que es lo que se puede ejecutar en Bitvavo, y con su coste real (0,15 %
  con orden limitada).

Criterio del clon: Sharpe en B por encima de mantener BTC en +0,10 y por encima del p95 del placebo.

## 3C · Congresistas, uno a uno

- **Datos**: las declaraciones de operaciones (PTR) de la Cámara y del Senado, públicas por ley. El Senado exige
  aceptar sus condiciones de uso en el navegador; eso lo acepta el user, no yo.
- **Sin mirar al futuro**: cada operación se compra en la **fecha de su declaración**, no en la de la operación (el
  retraso legal es de hasta 45 días), y se mantiene 6 meses.
- **Elegir a quién**: cada trimestre, con los 24 meses anteriores y sólo ellos, los congresistas cuyas operaciones
  declaradas mejor habrían rendido; se copia al decil superior.
- **Concretado el 31-oct, antes de analizar ninguna operación**: sólo se copian las **compras** (se puede comprar,
  no ponerse corto); cada una pesa por el centro de su tramo legal de importe (robustez: a partes iguales). El
  historial de un congresista es la rentabilidad media a 6 meses, desde su fecha de declaración, de sus compras
  declaradas en los 24 meses anteriores (mínimo 5). Sólo acciones con símbolo: las opciones, bonos y fondos de las
  declaraciones no entran, y se informa de su parte. Las declaraciones en papel escaneado no se leen, y se informa de
  cuántas son. Precios: los de Alpaca, con el mismo módulo y la misma comprobación de entidad que 2B.
- **Pasa sólo si se cumplen las tres**: frente al SPY, Sharpe +0,10 y CAGR +1 pp en las dos mitades; por encima del
  p95 de un placebo (congresistas al azar, 200 repeticiones); y por encima de NANC en el mismo periodo.

## Qué me probaría equivocado

Que en 3A los buenos de A no se distingan del azar en B (cierra Hyperliquid); que en 3C elegir congresistas no gane
al placebo ni a NANC (cierra el Congreso). Cada «no» se publica con el número que lo decidió.

## Qué NO se hace

Ni copiar posiciones en vivo, ni dinero real, ni aceptar condiciones de uso en nombre del user, ni cambiar un criterio
después de ver el dato que decide.
