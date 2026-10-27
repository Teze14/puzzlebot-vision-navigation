# Instalación y ejecución

[Volver al README](../README.md)

## Entorno y recursos necesarios

Los autores reportan ROS 2 Humble. Los comandos siguientes están escritos para Bash en Linux con Humble instalado; la versión exacta del sistema operativo, el equipo de cómputo y las versiones de bibliotecas usadas en las pruebas originales están pendientes de registrar.

| Recurso | Estado en esta entrega |
|---|---|
| Paquete `puzzlebot_follower` | Incluido. |
| ROS 2 Humble, herramientas de compilación `colcon` y `rosdep` | Deben estar instalados en el equipo de ejecución. |
| Paquete `my_interfaces` | Externo; el reporte documenta sus campos `bool`, pero faltan las fuentes del paquete o un enlace de instalación. |
| Checkpoint de detección | Externo; falta el archivo `.pt` entrenado para las clases del proyecto. |
| Cámara y controlador de la base Puzzlebot | Externos; sus comandos de inicio no están incluidos. |
| Entorno gráfico para OpenCV | Necesario: los nodos llaman a `cv2.imshow` sin opción para desactivarlo. |

La carpeta por sí sola todavía no permite reproducir el sistema completo. No se sustituye el modelo personalizado por uno genérico: debe reconocer las [etiquetas que espera el código](ARQUITECTURA.md).

## 1. Organizar el workspace

```bash
source /opt/ros/humble/setup.bash
mkdir -p ~/ros2_ws/src
```

Copiar la carpeta del repositorio dentro de `~/ros2_ws/src/`. Colocar también el paquete original `my_interfaces`, salvo que ya esté instalado en un entorno ROS cargado. La estructura esperada es:

```text
ros2_ws/
└── src/
    ├── puzzlebot_follower/
    │   ├── package.xml
    │   ├── setup.py
    │   ├── config/
    │   └── ...
    └── my_interfaces/       # Recuperar el paquete original
```

El `package.xml` del proyecto debe quedar directamente dentro de `src/puzzlebot_follower`, evitando una carpeta contenedora adicional por la extracción del archivo ZIP.

## 2. Resolver dependencias

Con `rosdep` ya inicializado en el equipo:

```bash
cd ~/ros2_ws
rosdep update
rosdep install --from-paths src --ignore-src --rosdistro humble -y
```

El manifiesto declara `rclpy`, `sensor_msgs`, `std_msgs`, `cv_bridge`, `geometry_msgs` y `my_interfaces`. El código también requiere NumPy y OpenCV; la ruta de detección requiere Ultralytics y su entorno de inferencia compatible. El lanzamiento importa `ament_index_python`, `launch` y `launch_ros`. La alternativa difusa requiere `scikit-fuzzy`.

**Las dependencias no están completamente declaradas:** `setup.py` solo instala `setuptools`, y el manifiesto no enumera todas las bibliotecas anteriores. Por ello, ejecutar `rosdep` o instalar el paquete no garantiza resolverlas todas. Recuperar las versiones del entorno original e instalarlas en el mismo intérprete usado por ROS antes de probar el sistema. No se incluye un archivo de versiones fijadas porque esas versiones aún no se conocen.

Comprobación inicial de importaciones para los nodos del lanzamiento principal:

```bash
python3 -c "import rclpy, cv2, numpy, ultralytics, ament_index_python, launch, launch_ros"
```

Esto comprueba disponibilidad, no compatibilidad completa ni funcionamiento del modelo. La documentación oficial de [Ultralytics para Python](https://docs.ultralytics.com/usage/python/) explica la carga de checkpoints y la inferencia; no determina qué versión se utilizó aquí.

## 3. Configurar el modelo

Editar `config/params.yaml` y reemplazar la ruta local original de `cnn_detector.ros__parameters.model_path` por la ruta absoluta al checkpoint real del equipo:

```yaml
cnn_detector:
  ros__parameters:
    model_path: "/ruta/real/al/modelo.pt"
    confidence_threshold: 0.75
```

La ruta anterior es ilustrativa. Comprobar que `model.names` contiene las etiquetas exactas de la tabla de arquitectura. Un nombre de archivo que contenga `100epoch` no acredita por sí solo el historial de entrenamiento.

## 4. Compilar

```bash
cd ~/ros2_ws
colcon build --symlink-install --packages-up-to puzzlebot_follower
source install/setup.bash
ros2 pkg executables puzzlebot_follower
ros2 interface show my_interfaces/msg/ColorStatus
ros2 interface show my_interfaces/msg/SignStatus
```

Los ejecutables esperados son `line_detector`, `final_detector`, `cnn_detector` y `decision_logic`. La alternativa difusa no está registrada. Consultar los flujos de compilación y selección de paquetes en la [guía oficial de colcon](https://colcon.readthedocs.io/en/main/user/quick-start.html) y el comportamiento de [`--symlink-install`](https://colcon.readthedocs.io/en/main/reference/verb/build.html).

## 5. Comprobar la percepción antes de habilitar movimiento

Iniciar la fuente de cámara con las herramientas de la plataforma. El paquete no la inicia automáticamente. Verificar:

```bash
ros2 topic info /video_source/compressed --verbose
ros2 topic hz /video_source/compressed
```

Debe publicar `sensor_msgs/msg/CompressedImage`. Para probar únicamente la percepción, ejecutar cada nodo en una terminal con los entornos ROS y del workspace cargados:

```bash
ros2 run puzzlebot_follower final_detector
```

```bash
ros2 run puzzlebot_follower cnn_detector --ros-args \
  --params-file ~/ros2_ws/src/puzzlebot_follower/config/params.yaml
```

Comprobar las ventanas de depuración y los mensajes:

```bash
ros2 topic echo /line_error
ros2 topic echo /zebra_detected
ros2 topic echo /color_status
ros2 topic echo /sign_status
```

Cada comando `echo` permanece activo hasta interrumpirlo. Verificar que las respuestas cambian al cambiar realmente la escena; una frecuencia de mensajes no garantiza imágenes nuevas.

## 6. Iniciar el sistema integrado

Cerrar los detectores iniciados manualmente para evitar duplicados. Con los componentes externos preparados:

```bash
source /opt/ros/humble/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch puzzlebot_follower followe.launch.py
```

Este comando inicia también el controlador, que puede publicar movimiento aun sin una línea válida. Para la primera verificación, mantener la base sin posibilidad de desplazarse y comprobar el sentido del giro, la recepción de imágenes y el mecanismo de parada de la plataforma. El código no implementa un watchdog de cámara ni una parada explícita al cerrar el nodo; comprobar el timeout de comandos del controlador de la base.

Para inspeccionar el sistema:

```bash
ros2 node list
ros2 topic info /cmd_vel --verbose
ros2 topic echo /cmd_vel
ros2 param get /puzzlebot_decision_logic max_v
```

Si se modifica `params.yaml`, reconstruir y volver a cargar el workspace cuando sea necesario para actualizar la configuración instalada. No se ha comprobado aquí una ejecución en ROS ni en hardware.

## Diagnóstico

| Síntoma | Comprobación |
|---|---|
| `No module named my_interfaces` | Recuperar y compilar el paquete original; cargar su entorno y verificar ambas interfaces. |
| Error de carga del modelo | Comprobar ruta, archivo, versión compatible de Ultralytics y dependencias del checkpoint. |
| El detector publica todo falso | Verificar que realmente cargó un modelo, recibe imágenes, reconoce las etiquetas y supera el umbral. |
| No hay imágenes | Comprobar nombre y tipo del tópico, publicación de la cámara y compatibilidad QoS. |
| Fallo de `imshow` | Usar una sesión gráfica y OpenCV con soporte GUI; no hay modo sin ventanas implementado. |
| No se inicia una maniobra | Revisar confirmación de señal, cebra, estado actual y un mensaje verde recibido después de entrar en espera. |
| Giro inesperado | El reporte describe una cámara reflejada horizontalmente; comprobar que la configuración actual conserva esa convención de `_pd_steering`. |
| Se repiten detecciones con cámara congelada | Los nodos reutilizan la última imagen; falta una comprobación de antigüedad. |
| El robot sigue avanzando al perder la línea | El detector publica error cero cuando no encuentra un contorno válido. |
