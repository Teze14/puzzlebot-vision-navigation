# Validación, limitaciones y evaluación pendiente

[Volver al README](../README.md)

## Evidencia disponible

| Aspecto | Estado |
|---|---|
| Entorno ROS | ROS 2 Humble, confirmado por uno de los autores. |
| Implementación | Código de percepción, control y lanzamiento disponible para inspección. |
| Frecuencia de control y visión | Temporizadores de 0.05 s en el código; frecuencia real no medida en esta revisión. |
| Ejecución sobre el robot | No verificada durante la preparación de esta documentación. |
| Reporte técnico | Aportado por el equipo; junio de 2026. Incluye diagramas, protocolos y resultados resumidos. |
| Video, recorridos y registros | No incluidos entre los archivos recibidos. |
| Modelo y datos de entrenamiento | No incluidos. |
| Precisión, latencia y éxito de recorridos | El reporte contiene cifras resumidas y metas; no se aportan logs ni tablas por ensayo. Ver la distinción siguiente. |
| Pruebas existentes | Pruebas de estilo `flake8` y `pep257`; prueba de copyright marcada para omitirse. No hay pruebas funcionales de navegación. |

El reporte constituye evidencia documental del trabajo del equipo. Sus cifras se atribuyen al documento; no se presentan como mediciones verificadas durante esta revisión.

## Resultados del reporte y metas

Las páginas citadas son las impresas en el documento; el número de página del archivo PDF es uno mayor.

| Ensayo | Lo que dice el reporte | Cómo se presenta aquí |
|---|---|---|
| Seguimiento con iluminación normal, reducida y solar directa (sección 4.1, p. 13) | «≥95 % de éxito»; el protocolo describe tres vueltas por condición. | Resultado reportado. Faltan conteos de éxitos y fallos por condición; tres intentos por condición no permiten reconstruir por sí solos un porcentaje de 95 %. |
| Señales y semáforos (sección 4.2, p. 13) | Detección confiable a ≥0.8 m; estable a ≥0.4 m; cero falsos positivos. | Resultado reportado sin desglose por clase, número de observaciones ni duración del ensayo sin señales. No equivale a precisión del 100 %. |
| Circuito completo (sección 4.3, p. 14) | **Resultado esperado:** ≥4 de 5 vueltas, cero infracciones de semáforo, tiempo <120 s. | Meta del experimento. No se convierte en resultado alcanzado, aunque la conclusión general describa navegación autónoma exitosa. |
| Latencia (secciones 3.3.1 y 5.1, pp. 9 y 14) | 100–300 ms por imagen de YOLO y menos de 50 ms de seguimiento. | Cifras narradas sin hardware, trazas o método de medición suficientes para reproducirlas; no se usan como un benchmark verificado. |

El reporte anuncia cinco experimentos y desarrolla tres apartados. Para cerrar la evaluación conviene incorporar los registros originales y precisar cuáles pruebas se realizaron y cuáles quedaron propuestas. La [nota de procedencia](REPORTE.md) identifica otras diferencias entre reporte y código.

## Limitaciones observadas en el código

| Observación | Consecuencia | Mejora propuesta |
|---|---|---|
| Error cero cuando no se detecta línea e inicialización del controlador en cero | Pérdida de línea o falta de percepción pueden confundirse con alineación correcta. | Publicar validez de detección y detener ante pérdida o falta de datos. |
| Reutilización de la última imagen sin comprobar antigüedad | Una cámara congelada puede seguir generando señales y comandos. | Registrar edad o secuencia y exigir imágenes recientes. |
| Comentario y signo de `_pd_steering` no coinciden | El reporte explica el signo positivo por una cámara reflejada horizontalmente. | Actualizar el comentario y verificar la convención cuando cambie el montaje o la cámara. |
| Rojo se libera por timeout y no detiene `MANEUVER` | El comportamiento no representa una retención indefinida ante semáforo rojo. | Definir y probar una política explícita para pérdida de semáforo y maniobras. |
| La espera de intersección termina volviendo a seguimiento sin verde | Agotar el tiempo puede causar movimiento sin una nueva autorización visual. | Revisar la política de recuperación con el equipo. |
| Aproximación y maniobras sin realimentación | Sensibilidad a batería, fricción y posición inicial. | Incorporar odometría o referencias visuales durante la maniobra. |
| Tiempo de estado acumulado por ciclos fijos | La duración real cambia si se retrasa el procesamiento. | Medir tiempo transcurrido con el reloj adecuado. |
| Falta de parada explícita en el cierre y watchdog interno | La detención depende también del controlador externo de la base. | Implementar y verificar timeout de comandos y secuencia de apagado. |
| Dependencias y recursos externos incompletos | La carpeta aún no ofrece una reproducción completa. | Publicar interfaces, versiones, instrucciones de hardware y checkpoint. |

Son hallazgos de inspección estática, no fallos reproducidos experimentalmente durante esta revisión. El alcance de esta entrega es documentar el comportamiento; no se modificó el algoritmo.

## Plan de evaluación reproducible

Registrar primero el equipo, sistema operativo, versión de Python, dependencias, cámara, resolución, iluminación, geometría de pista, parámetros y revisión de código. Guardar la configuración de cada ensayo para no comparar ejecuciones con condiciones distintas sin indicarlo.

| Ensayo | Evidencia a guardar | Métrica sugerida |
|---|---|---|
| Seguimiento de línea en rectas y curvas | Video continuo, `/line_error`, comandos y anotación de pérdida de línea | Recorridos completados / intentos, salidas de pista, error absoluto medio en muestras válidas. |
| Señales y semáforos | Imágenes etiquetadas de prueba, predicciones y umbral | Precisión y recall por clase; falsos positivos por recorrido. |
| Cruce tipo cebra | Escenas con y sin cebra, incluyendo otros patrones oscuros | Detecciones correctas, falsas activaciones y omisiones. |
| Intersecciones | Video y registros de cambios de estado | Maniobras completadas / intentos por dirección. |
| Latencia | Marcas de tiempo de captura, recepción, inferencia y decisión | Mediana y percentil 95 por etapa, sobre hardware identificado. |
| Pérdida de cámara o línea | Ensayo controlado con la base inmovilizada | Comandos tras la pérdida y tiempo hasta detenerse, si existe. |

Las métricas son propuestas, no resultados. Al calcular error medio, excluir o marcar explícitamente las muestras inválidas: el error cero actual no permite distinguir una línea centrada de una pérdida.

El cuadro 4 del reporte describe mensajes personalizados con campos booleanos y no muestra timestamps. La medición de latencia de extremo a extremo requerirá instrumentación adicional y correlación entre imágenes y resultados, además de comprobar las definiciones originales.

## Registro de una prueba

Para capturar tópicos con las herramientas de grabación de ROS 2 instaladas:

```bash
ros2 bag record -o ensayo_01 \
  /video_source/compressed /line_error /zebra_detected \
  /color_status /sign_status /line_reset /cmd_vel
```

La máquina de estados escribe transiciones en el logger; no publica un tópico de estado. Conservar también esos logs o añadir instrumentación en una mejora posterior. Las grabaciones y pesos están excluidos por `.gitignore`; pueden distribuirse por un medio separado con un enlace y una descripción de su contenido.

## Ejecutar las pruebas existentes

En un workspace ROS completo y compilado:

```bash
colcon test --packages-select puzzlebot_follower
colcon test-result --verbose
```

Estas pruebas revisan estilo y documentación de código; no demuestran desempeño del robot. No se ejecutaron aquí, por lo que no se afirma que pasen. Para una explicación del flujo de pruebas, consultar la [referencia oficial de colcon](https://colcon.readthedocs.io/en/main/user/quick-start.html).

## Demostración para el portafolio

Incluir un video breve donde se vea el robot y la pista, seguido de una vista de las detecciones y una explicación de una decisión técnica. Mostrar un recorrido continuo ayuda a distinguir una demostración completa de una colección de tomas aisladas. Acompañarlo con el entorno, la configuración y los límites observados; evitar atribuir precisión o autonomía que no se haya medido.
