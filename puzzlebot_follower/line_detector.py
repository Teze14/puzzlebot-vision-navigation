#!/usr/bin/env python3
import rclpy
import cv2
import numpy as np
from rclpy.node import Node
from cv_bridge import CvBridge
from sensor_msgs.msg import Image
from std_msgs.msg import Float32
from rclpy import qos

class LineFollowerVision(Node):
    def __init__(self):
        super().__init__("line_follower_vision")
        self.get_logger().info("Nodo de Visión de Línea Iniciado - Puzzlebot Challenge")

        # Herramientas de OpenCV y ROS2
        self.bridge = CvBridge()
        self.img = None
        self.last_cx = None  # última posición detectada para continuidad
        
        # Suscripción a la fuente de video del Puzzlebot [cite: 8]
        self.sub = self.create_subscription(
            Image, 
            "/video_source/raw", 
            self.camera_callback, 
            qos.qos_profile_sensor_data)
        
        # Publicador del error de línea para el controlador [cite: 21]
        self.error_pub = self.create_publisher(Float32, "line_error", 10)
        
        # Timer de procesamiento (20 FPS para buena respuesta)
        self.create_timer(0.05, self.process_image)

    def camera_callback(self, msg):
        """Convierte el mensaje de ROS a formato OpenCV."""
        self.img = self.bridge.imgmsg_to_cv2(msg, 'bgr8') 

    def process_image(self):
        """Algoritmo de detección de línea robusto."""
        if self.img is None:
            return

        frame = self.img.copy()
        height, width, _ = frame.shape

        # 1. REGIÓN DE INTERÉS (ROI) [cite: 10]
        # Enfocamos la vista en el suelo frente al robot (franja del 60% al 100%)
        roi_start = int(height * 0.6)
        roi_end = int(height * 1.0)
        roi = frame[roi_start:roi_end, :]

        # 2. PRE-PROCESAMIENTO PARA ROBUSTEZ 
        # Convertimos a escala de grises y aplicamos Blur para reducir ruido
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Umbralización de Otsu: se adapta automáticamente a los cambios de luz 
        # THRESH_BINARY_INV asume que la línea es más oscura que el suelo
        _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # 3. FILTRADO DE CONTORNOS
        # Buscamos todos los objetos blancos en la máscara
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        error_to_publish = 0.0

        # Área mínima para descartar ruido (ajustar según resolución de cámara)
        MIN_AREA = 500
        center_img = width // 2

        valid_contours = [c for c in contours if cv2.contourArea(c) > MIN_AREA]

        if valid_contours:
            # Calculamos el centroide de cada contorno válido
            candidates = []
            for c in valid_contours:
                M = cv2.moments(c)
                if M['m00'] > 0:
                    cx = int(M['m10'] / M['m00'])
                    candidates.append((cx, c))

            if candidates:
                # Referencia: última posición conocida o centro de imagen si es la primera vez
                ref_x = self.last_cx if self.last_cx is not None else center_img

                # Seleccionamos el contorno cuyo centroide esté más cerca de la referencia
                cx, best_contour = min(candidates, key=lambda item: abs(item[0] - ref_x))

                # Limitar el salto máximo por frame para no engancharse con otra línea en curvas
                # Si el salto es mayor al 20% del ancho, avanzamos solo hasta ese límite
                MAX_JUMP = int(width * 0.20)
                if self.last_cx is not None and abs(cx - self.last_cx) > MAX_JUMP:
                    cx = self.last_cx + int(np.sign(cx - self.last_cx) * MAX_JUMP)

                self.last_cx = cx

                # 4. CÁLCULO DEL ERROR NORMALIZADO
                error_to_publish = float(cx - center_img) / (width / 2)

                # Visualización para debug
                cv2.drawContours(roi, [best_contour], -1, (0, 255, 0), 2)
                cv2.circle(roi, (cx, (roi_end - roi_start) // 2), 7, (0, 0, 255), -1)

        # Publicamos el error para el nodo de decisión/control [cite: 19]
        msg_error = Float32()
        msg_error.data = error_to_publish
        self.error_pub.publish(msg_error)
        
        # Ventanas de visualización
        cv2.imshow("Mascara (Otsu)", thresh)
        cv2.imshow("Deteccion Robusta", roi)
        cv2.waitKey(1)

def main(args=None):
    rclpy.init(args=args)
    node = LineFollowerVision()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.try_shutdown()

if __name__ == '__main__':
    main()