# Parámetros y ajustes

[Volver al README](../README.md)

El lanzamiento carga `config/params.yaml` para el controlador y el detector YOLO. Los valores del YAML sustituyen los predeterminados del constructor. La visión de línea usa constantes internas y no recibe ese archivo.

Las tablas se contrastaron con las declaraciones del código y el YAML de esta entrega. Los tiempos nominales dependen del número de ciclos; no son mediciones de duración real.

## `puzzlebot_decision_logic`

| Parámetro | Constructor | YAML activo | Unidad / interpretación | Uso |
|---|---|---|---|---|
| `kp` | `0.8` | `1.0` | Ganancia | Término proporcional del giro. |
| `kd` | `0.1` | `0.1` | Ganancia por diferencia entre ciclos | No usa una derivada dividida entre segundos. |
| `max_v` | `0.2` | `0.15` | m/s | Velocidad base durante seguimiento; no limita globalmente las maniobras. |
| `yellow_speed_factor` | `0.4` | `0.4` | Fracción | Reducción por amarillo en FOLLOWING. |
| `roadwork_speed_factor` | `0.5` | `0.5` | Fracción | Reducción en ROADWORK_SLOW. |
| `give_way_speed_factor` | `0.3` | `0.3` | Fracción | Solo se usa en GIVE_WAY_APPROACH, estado sin transición de entrada actual. |
| `approach_speed_factor` | `0.4` | `0.7` | Fracción | Preaproximación y avance recto en INTERSECTION_APPROACH. |
| `maneuver_linear_v` | `0.15` | `0.15` | m/s | Avance durante maniobras; glorieta usa el 70 %. |
| `maneuver_angular_w` | `0.8` | `0.8` | rad/s | Izquierda positiva, derecha negativa; glorieta usa el 50 % positivo. |
| `stop_hold_time` | `3.0` | `3.0` | s nominales | Espera de alto, acumulada por ciclos. |
| `approach_time` | `2.5` | `2.5` | s nominales | Duración de aproximación, acumulada por ciclos. |
| `maneuver_straight_time` | `1.5` | `2.5` | s nominales | Duración de maniobra recta. |
| `maneuver_turn_time` | `3.0` | `2.4` | s nominales | Duración de giro o glorieta. |
| `sign_confirm_count` | `5` | `5` | Mensajes acumulados | Umbral de contador con incremento y decremento; no exige detecciones consecutivas. |
| `roadwork_timeout` | `3.0` | `3.0` | s de reloj ROS | Tiempo desde la última confirmación acumulada de obras. |
| `sign_cooldown_time` | `5.0` | `5.0` | s de reloj ROS | Periodo de inhibición de alto después de STOP_HOLD. |
| `red_timeout` | `1.5` | `1.5` | s de reloj ROS | Libera retención si no vuelve a detectarse rojo. |
| `intersection_wait_timeout` | `10.0` | `10.0` | s nominales | Al vencer, abandona la espera y vuelve a FOLLOWING sin exigir verde. |

## `cnn_detector`

| Parámetro | Constructor | YAML activo | Unidad / interpretación | Uso |
|---|---|---|---|---|
| `model_path` | `""` | `Ruta local original` | Ruta | Reemplazar la ruta absoluta original por el checkpoint real; no está incluido. |
| `confidence_threshold` | `0.75` | `0.75` | Confianza | Se copia al iniciar el detector; reiniciar para aplicar un cambio. |

## Constantes de visión

| Ajuste | Valor actual |
|---|---|
| Inicio de la región inferior | 60 % de la altura |
| Periodo de procesamiento | 0.05 s |
| Área mínima de línea | Mayor a 500 px² |
| Salto máximo del centroide | 20 % del ancho, convertido a entero |
| Área de candidato a cebra | 150 a 20 000 px² |
| Relación ancho/alto mínima | 1.3 |
| Ancho mínimo del candidato | 5 % del ancho de imagen, convertido a entero |
| Candidatos requeridos de cebra | 6 |
| Confirmación de cebra | Contador ≥ 3, saturado en 6 |

Cambiar estas constantes requiere editar `line_colors_detector.py`; no son parámetros ROS configurables.

## Ejemplo de interpretación

Con el YAML actual, en FOLLOWING sin reducción por señal, un error cero produce una velocidad lineal de 0.15 m/s; un error de magnitud 1 la reduce a 0.015 m/s. Son resultados de la fórmula, no mediciones. La aproximación recta usa `0.15 × 0.7 = 0.105 m/s` y una duración nominal de 2.5 s. La maniobra de giro usa 0.15 m/s y magnitud angular de 0.8 rad/s durante 2.4 s nominales. No se garantiza un ángulo final: no hay corrección por odometría.

## Criterio de ajuste

Comprobar primero la validez de percepción y el sentido del giro. Después ajustar las ganancias con velocidad baja, registrar el error y cambiar una variable a la vez. Ajustar la geometría de cebra según resolución y perspectiva. Calibrar las maniobras por separado y conservar la configuración usada en cada ensayo. El código no añade validación de rangos para estos parámetros.
