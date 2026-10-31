# Resultados de la fase 2A: el control, *Buffett's Alpha* con datos públicos (2026-10-31)

Criterio fijado antes de bajar los datos en [PLAN_FASE2.md](PLAN_FASE2.md) (`ac57fb5`). Código:
`python -m tiresias.buffett`. Aquí sólo hay coeficientes: ningún precio.

**Veredicto: el control pasa, 3 de 3.** Con datos públicos, Berkshire se descompone casi como en el artículo: el alfa
deja de ser significativo al añadir la baja beta (BAB) y la calidad (QMJ). La fase 2 sigue.

## La tabla 4, reproducida

Exceso mensual de BRK-A sobre el tipo libre, **1980-04 → 2011-12, 381 meses** (el artículo, con CRSP, desde 1976-11).
Factores de la biblioteca de Ken French (MKT, SMB, HML, UMD, tipo libre) y de la de AQR (BAB y QMJ de EE. UU.).
Coeficiente, t entre paréntesis y, entre corchetes, el publicado.

| | columna 1 (4 factores) | columna 2 (+ BAB) | columna 3 (+ BAB + QMJ) |
|---|---|---|---|
| alfa anual | **10,0 %** (2,68) [12,1 %] | 7,9 % (2,02) [9,2 %] | 4,0 % (**1,02**) [6,3 %] |
| MKT | 0,79 (10,96) [0,84] | 0,79 (11,28) [0,83] | 0,92 (10,60) [0,95] |
| SMB | −0,38 (−3,67) [−0,32] | −0,40 (−3,90) [−0,32] | −0,24 (−2,05) [−0,15] |
| HML | 0,41 (3,66) [0,63] | 0,19 (1,55) [0,38] | 0,31 (2,36) [0,46] |
| UMD | 0,04 (0,64) [0,06] | −0,04 (−0,63) [−0,03] | −0,09 (−1,21) [−0,05] |
| BAB | | 0,35 (3,96) [0,37] | **0,29** (3,24) [0,29] |
| QMJ | | | **0,47** (2,46) [0,43] |
| R² ajustado | 0,25 [0,25] | 0,28 [0,27] | 0,29 [0,28] |

## Los tres criterios

| | criterio | resultado |
|---|---|---|
| 1 | en la columna 3, MKT, HML, BAB y QMJ a ±0,15 del publicado | ✓ — MKT −0,030 · **HML −0,149** · BAB +0,003 · QMJ +0,039 |
| 2 | BAB y QMJ positivos con t ≥ 2 | ✓ — t 3,24 y 2,46 |
| 3 | alfa de cuatro factores con t ≥ 2, y de seis con t < 2 | ✓ — 2,68 y 1,02 |

**Lo que hay que decir**: HML pasa por 0,001. Es la carga que más se aleja (0,31 frente a 0,46), y su causa probable
es la que el plan declaraba: faltan 1976–1980, los años de las grandes compras «de valor» de Buffett, y las series se
revisan (AQR reconstruye toda su historia en cada actualización; French también revisa la suya). BAB y QMJ, las dos
que importan para la tesis del artículo, salen casi exactas.

**Control negativo**: con la serie de Berkshire desplazada un mes, la columna 3 da BAB 0,22, QMJ 0,00 y MKT 0,17, y el
control, 0 de 3. El verificador puede fallar.

**Datos** (con su sha256 fuera del repo): BRK-A diario de Yahoo (11.752 sesiones, 1980-03-17 → 2026-10-30, sin
dividendos); `F-F_Research_Data_Factors` y `F-F_Momentum_Factor` (CRSP 202609); las hojas «BAB Factors» y «QMJ Factors»
de AQR, columna USA, descargadas el 31-oct-2026. Tests: 13, con 6 mutantes que mueren.

## Siguiente: 2A′

Las cargas de la columna 3, congeladas con 1980–2011, y la estrategia sistemática del artículo de 2012 en adelante:
¿sigue viva la receta después de publicarse?
