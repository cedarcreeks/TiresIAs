# TiresIAs · Fase 3 · Resultados (en curso)

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

## 3C · Congresistas uno a uno

En curso: 6.989 declaraciones de operaciones de la Cámara (2016–2026) bajadas del Clerk; el analizador de los PDF y la
cartera están escritos y probados. Faltan los precios y el juicio.
