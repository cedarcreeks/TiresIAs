# TiresIAs · Fase 2 · Ingeniería inversa de los mejores gestores — plan y criterios, fijados ANTES de medir (2026-10-31)

Este documento se publica antes de bajar ningún dato de la fase 2: el historial de git fecha cada criterio. Si un
criterio cambia, cambia en un commit nuevo, con su porqué y antes de ver el dato que decide.

## La pregunta

**¿Se puede convertir lo que hace ganar a los mejores gestores en una regla sistemática, barata y pública, que bata al
S&P 500 fuera de la muestra en la que se descubrió?**

No se copian sus posiciones: eso ya existe y fue mal. El ETF GURU copia las posiciones más concentradas de grandes
hedge funds desde 2012 y en los últimos 10 años rinde 5,9 % al año frente a 10,8 % del S&P 500
([PortfoliosLab](https://portfolioslab.com/tools/stock-comparison/GURU/SPY)). Se copia **la receta**: a qué factores
se exponen y con cuánto apalancamiento, que es lo que explica la mayor parte de lo que ganan.

## El método, el de sus autores

[*Buffett's Alpha*](https://papers.ssrn.com/abstract=3197185) (Frazzini, Kabiller y Pedersen; NBER w19681, 2013;
*Financial Analysts Journal* 2018), secciones 6 y 7, tablas 4 y 5:

1. Regresión mensual del exceso de rentabilidad sobre seis factores: mercado (MKT), tamaño (SMB), valor (HML),
   momentum (UMD), baja beta (BAB, Frazzini y Pedersen 2013) y calidad (QMJ, Asness, Frazzini y Pedersen 2013).
2. Con los dos últimos, el alfa de Berkshire deja de ser significativo: compra acciones **baratas, seguras y de
   calidad**, con un apalancamiento de ≈ 1,6 a 1 (el *float* de las aseguradoras).
3. La «estrategia sistemática de Buffett»: la parte que explican los factores, reescalada a la volatilidad
   idiosincrática de Berkshire (lo que simula su apalancamiento), más su exposición al mercado y el tipo libre. Los
   autores avisan: sin costes y con la ventaja de mirar hacia atrás.

## 2A · Control: reproducir la tabla 4 con datos públicos

**Datos**: Berkshire (BRK-A, cierres mensuales); MKT, SMB, HML, UMD y el tipo libre, de la biblioteca de Ken French;
BAB y QMJ de EE. UU., de la biblioteca de datos de AQR. **Diferencia declarada**: el artículo usa CRSP desde 1976-11;
aquí, 1980-04 → 2011-12 (la serie pública de BRK-A empieza en 1980).

**Objetivo** (tabla 4, Berkshire 1976–2011): columna 1 (cuatro factores), alfa 12,1 % (t 3,19); columna 3 (seis
factores), alfa 6,3 % (t 1,58), MKT 0,95, SMB −0,15, HML 0,46, UMD −0,05, BAB 0,29 (t 2,67), QMJ 0,43 (t 2,34).

**Pasa sólo si se cumplen las tres**: (1) en la columna 3, MKT, HML, BAB y QMJ a ±0,15 de su valor publicado; (2) BAB
y QMJ positivos con t ≥ 2; (3) el alfa de cuatro factores con t ≥ 2 y el de seis con t < 2. **Si no pasa, la fase se
para** hasta entender por qué (datos, montaje o un cambio de las series desde 2013): sin control no hay fase 2B.

## 2A′ · ¿Sigue viva la receta de Buffett después de publicarse?

Las cargas se estiman con 1980–2011 y **se congelan**; la estrategia sistemática se mide de 2012-01 a la última serie
disponible (el artículo salió en noviembre de 2013). Se informa frente a Berkshire y frente al mercado. Lo publicado
suele perder la mitad tras publicarse (McLean y Pontiff, *JF* 2016): **la receta sigue viva** si su Sharpe supera al del
mercado en ≥ 0,10 en 2012→ y en cada mitad del periodo. Si no, se dice y se pasa a 2B igualmente (2B no depende de
Buffett).

## 2B · Lo genérico: la receta de los mejores gestores

- **Gestores**: los que presentan formularios 13F a la SEC (conjuntos de datos estructurados, trimestrales). Su cartera
  se reconstruye como en la tabla 4: las posiciones del último 13F, pesos por valor, reequilibrio mensual a pesos
  constantes, **compradas el día en que el 13F se publica** (hasta 45 días después del trimestre), nunca antes.
- **Precios**: diarios y con los valores que dejaron de cotizar (sin sesgo de supervivencia), desde 2016.
- **Elegir sin mirar al futuro**: en cada trimestre, con los 36 meses anteriores y sólo ellos, la regresión de seis
  factores de cada gestor; elegidos, el decil superior por la t de su alfa (mínimo 36 meses de historia).
- **La receta**: las cargas medias de los elegidos, aplicadas a los factores del trimestre siguiente, reescaladas como
  en 2A. Coste estimado de implementarla: 0,5 % al año.
- **Periodo de juicio**: 2019-01 en adelante (tres años de calentamiento desde 2016).

**Pasa sólo si se cumplen las cuatro**: (1) frente al S&P 500 con dividendos, Sharpe +0,10 y CAGR +1 pp al año, netos
del coste estimado; (2) en las dos mitades del periodo; (3) por encima del percentil 95 de un placebo (el mismo
procedimiento con gestores elegidos al azar, 200 repeticiones); (4) por encima de la receta de **todos** los gestores en
≥ 0,05 de Sharpe: elegir tiene que aportar. Se informan también, como comparación, copiar las posiciones (las cinco de
mayor peso de cada elegido, como las «mejores ideas» de Cohen, Polk y Silli) y el ETF GURU real.

## 2C · Hecha con lo que se puede comprar

Sólo si 2B pasa: la receta con ETF de factores sólo a largo (calidad, mínima volatilidad, valor, momentum, tamaño) y el
apalancamiento disponible, con costes e impuestos reales. Si pasa, va a una incubadora **en sombra**: señales
registradas antes del resultado, regla congelada. Nada de dinero hasta que pase allí.

## ¿Lo mejoraría un modelo (IA)?

Sólo después de 2B, y sólo si 2B muestra señal: un modelo que prediga **qué recetas persisten**. Antes, su techo con un
oráculo (las cargas del trimestre siguiente, reales): si ni el oráculo bate al S&P por el margen de 2B, no hay modelo
que lo haga. La fase 1 de este repo es el recordatorio (Kronos, 0 de 5).

## Qué me probaría equivocado

Que el control 2A no reproduzca el artículo (entonces nada de lo que siga es de fiar); que la receta de Buffett haya
muerto tras publicarse; que en 2B la selección no gane al placebo ni a «todos los gestores». Cualquiera de ellos cierra
o para su línea, con el número que lo decidió.

## Qué NO se hace

Ningún dato en el repo (sólo agregados); ni elegir gestores mirando su resultado; ni cambiar un criterio después de
ver el dato que decide; ni ingeniería inversa de software ajeno; ni dinero real.
