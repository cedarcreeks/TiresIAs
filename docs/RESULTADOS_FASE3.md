# TiresIAs · Fase 3 · Resultados

Plan y criterios: [PLAN_FASE3.md](PLAN_FASE3.md), fijados antes de bajar los datos.

## 3A · Hyperliquid: NO (1 de 2) — a los que les va mejor ahora no les sigue yendo mejor

Muestra de 6.000 cuentas al azar (semilla 31) de la clasificación pública del 31-oct-2026; las 6.000 curvas, sin un
error. Universo del plan: 1.597 cuentas con al menos 10.000 $ al empezar A y actividad en A y en B. Rentabilidad =
resultado de la ventana entre el patrimonio medio (las aportaciones y retiradas no cuentan).

| Criterio | | |
|---|---|---|
| 1 · Spearman entre A (nov-2025 → abr-2026) y B (may → oct-2026) > 0 con p < 0,01 | ρ = 0,117, p < 0,0001 | sí |
| 2 · El decil superior de A, en B, por encima del p95 del placebo | mediana +19,2 %; placebo: mediana +39,6 %, p95 +50,7 % | **no** |

**Elegir a los diez por ciento mejores de A habría rendido en B la mitad que elegir al azar.** El sesgo que se declaró
(la clasificación sólo lista cuentas que existen hoy) favorecía la persistencia, así que el «no» es fuerte. Por el
plan, **3B no se construye**: no hay persistencia que imitar.

**De dónde sale la correlación (exploratorio, no decide nada).** Mediana de B por decil de A:

| decil de A | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| mediana en A | −667 % | −203 % | −101 % | −47 % | −30 % | −23 % | −16 % | −2 % | +13 % | +65 % |
| mediana en B | −0,2 % | +12 % | +31 % | +35 % | +60 % | +67 % | +58 % | +19 % | +25 % | +19 % |
| positivas en B | 48 % | 61 % | 64 % | 78 % | 88 % | 94 % | 87 % | 77 % | 81 % | 61 % |

Es una U invertida. Los dos extremos rinden peor en B: los que más perdieron y los que más ganaron en A, que suelen ser
los que más arriesgan. La correlación positiva sale de que los grandes perdedores siguen perdiendo, no de que los
ganadores sigan ganando. **Lo que se lleva quien lo lea: no seguir a los primeros de la clasificación.**

**Dónde queda flojo.**

- Seis meses por ventana: es un solo par A→B, y un régimen de mercado (B fue alcista para la mayoría).
- La curva de cada cuenta tiene unos 85–90 puntos desde su inicio: el patrimonio al empezar una ventana es el del
  punto anterior más cercano.
- Las cuentas que se arruinaron y se fueron pueden faltar de la clasificación.

## 3C · Congresistas de la Cámara: NO (0 de 3) — elegir a quién copiar no aporta

**Datos.**

- Las 6.989 declaraciones de operaciones de la Cámara de 2016 a 2026, del Clerk.
- 5.298 son electrónicas; las 1.691 de papel escaneado (24 %) no se leen y quedan fuera.
- De 51.761 operaciones, **17.305 son compras de acciones con símbolo**, de 205 congresistas en 2.191 símbolos.
- Tienen precio 16.650, de 202 congresistas: 1.911 símbolos por el camino de Alpaca, 28 reconstruidos, 8 descartados
  por el guardián y 244 sin datos.

**Método** ([plan](PLAN_FASE3.md)):

- cada compra entra al cierre del día de mercado siguiente a su presentación y se mantiene 182 días;
- cada trimestre se copia al decil superior de congresistas por la rentabilidad de sus compras de los 24 meses
  anteriores, sólo con tenencias ya acabadas, y con un mínimo de 5;
- hay decisión en los 34 trimestres de 2018 a 2026, con 3 a 5 elegidos.

Juicio de 2018-04 a 2026-08 (98 meses):

| | Sharpe | CAGR |
|---|---|---|
| Copiar a los elegidos, ponderado por importe | 0,63 | 17,7 % |
| Copiar a los elegidos, a partes iguales (robustez) | 0,38 | 9,9 % |
| S&P 500 con dividendos | 0,76 | 14,8 % |
| Placebo (congresistas al azar, 200 veces), mediana / p95 | 0,56 / 0,94 | — |
| En los 39 meses comunes con NANC: la copia / NANC | 0,07 / 1,22 | — |

| Criterio | |
|---|---|
| 1 · Sharpe +0,10 y CAGR +1 pp frente al S&P 500, en las dos mitades | **no** |
| 2 · Por encima del p95 del placebo | **no** |
| 3 · Por encima de NANC en el periodo común | **no** |

Ponderada por importe, la copia ganó más que el S&P 500 (+2,9 pp al año), pero con mucho más riesgo: Sharpe 0,63
frente a 0,76. Esa ganancia sale de unas pocas compras muy grandes y no se distingue de elegir congresistas al azar
(cae dentro del placebo). A partes iguales, la ventaja desaparece. Y en 2023–2026 queda muy por debajo de NANC, que
copia a todos los demócratas.

**Lo que se lleva quien lo lea**: ni copiar a todos (NANC: alfa 0,0) ni elegir a los «mejores» congresistas por su
historial bate al índice.

**Dónde queda flojo.**

- Sólo la Cámara: el Senado exige aceptar sus condiciones de uso.
- La cuarta parte de las declaraciones, en papel, no se lee.
- Con 3–5 elegidos por trimestre la cartera es muy concentrada.
- La rentabilidad de las acciones de importes grandes pesa mucho al ponderar por el centro del tramo.
