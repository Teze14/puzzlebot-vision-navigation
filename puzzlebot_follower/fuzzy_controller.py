#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32
from my_interfaces.msg import ColorStatus

import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

class FuzzyPuzzlebotController(Node):
    def __init__(self):
        super().__init__("puzzlebot_fuzzy_logic")
        
        # --- PARÁMETROS --- 
        self.declare_parameter("max_v", 0.2)
        
        # --- SUBSCRIPCIONES Y PUBLICACIONES ---
        self.pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.create_subscription(Float32, "/line_error", self.cb_line_error, 10)
        self.create_subscription(ColorStatus, "/color_status", self.cb_color, 10)

        # --- VARIABLES DE ESTADO ---
        self.line_error = 0.0
        self.last_error = 0.0
        self.held_by_red = False
        self.yellow_detected = False
        
        # --- CONFIGURACIÓN DEL SISTEMA DIFUSO ---
        self.setup_fuzzy_system()

        # Timer (20Hz)
        self.create_timer(0.05, self.control_loop)
        self.get_logger().info("Controlador Difuso de Puzzlebot Iniciado")

    def setup_fuzzy_system(self):
        # 1. Definir los universos de discurso (rangos de entrada y salida)
        # El error visual viene normalizado de -1.0 a 1.0 según tu nodo de visión
        e_universe = np.arange(-1.0, 1.1, 0.1)
        # La derivada (cambio de error) usualmente es menor, digamos de -0.5 a 0.5
        de_universe = np.arange(-0.5, 0.6, 0.1)
        # Salida del giro (steering) en rad/s, ajusta según la capacidad física del robot
        steer_universe = np.arange(-1.5, 1.6, 0.1)

        # 2. Crear las variables difusas (Antecedentes y Consecuentes)
        error = ctrl.Antecedent(e_universe, 'error')
        delta_error = ctrl.Antecedent(de_universe, 'delta_error')
        steering = ctrl.Consequent(steer_universe, 'steering')

        # 3. Funciones de pertenencia (Automáticas en 5 conjuntos: NB, NS, ZE, PS, PB)
        # NB = Negative Big, NS = Negative Small, ZE = Zero, PS = Positive Small, PB = Positive Big
        names = ['NB', 'NS', 'ZE', 'PS', 'PB']
        error.automf(names=names)
        delta_error.automf(names=names)
        steering.automf(names=names)

        # 4. Definir las reglas lógicas (Equivalente al comportamiento PD)
        # Ejemplo: Si el error es cero y no está cambiando, el giro es cero.
        rules = [
            ctrl.Rule(error['NB'] & delta_error['NB'], steering['PB']),
            ctrl.Rule(error['NB'] & delta_error['ZE'], steering['PB']),
            ctrl.Rule(error['NS'] & delta_error['ZE'], steering['PS']),
            
            ctrl.Rule(error['ZE'] & delta_error['NS'], steering['NS']),
            ctrl.Rule(error['ZE'] & delta_error['ZE'], steering['ZE']),
            ctrl.Rule(error['ZE'] & delta_error['PS'], steering['PS']),
            
            ctrl.Rule(error['PS'] & delta_error['ZE'], steering['NS']),
            ctrl.Rule(error['PB'] & delta_error['ZE'], steering['NB']),
            ctrl.Rule(error['PB'] & delta_error['PB'], steering['NB'])
        ]

        # 5. Construir el sistema de simulación
        steering_ctrl = ctrl.ControlSystem(rules)
        self.fuzzy_sim = ctrl.ControlSystemSimulation(steering_ctrl)

    def cb_line_error(self, msg):
        self.line_error = msg.data

    def cb_color(self, msg):
        if msg.red:
            self.held_by_red = True
        elif msg.green:
            self.held_by_red = False
        self.yellow_detected = msg.yellow

    def get_effective_velocity(self):
        max_v = self.get_parameter("max_v").get_parameter_value().double_value
        if self.held_by_red:
            return 0.0
        base_v = max_v * 0.4 if self.yellow_detected else max_v
        speed_factor = 1.0 - min(abs(self.line_error), 1.0) * 0.9
        return base_v * speed_factor

    def control_loop(self):
        msg = Twist()
        v_eff = self.get_effective_velocity()

        if v_eff > 0:
            # 1. Calcular derivada (Delta Error)
            d_error = self.line_error - self.last_error
            
            # Limitar d_error al universo definido para evitar errores en la librería
            d_error = max(min(d_error, 0.5), -0.5)

            # 2. Pasar inputs al sistema difuso
            self.fuzzy_sim.input['error'] = self.line_error
            self.fuzzy_sim.input['delta_error'] = d_error

            # 3. Ejecutar la inferencia matemática (Defuzificación por centroide por defecto)
            try:
                self.fuzzy_sim.compute()
                fuzzy_steering = self.fuzzy_sim.output['steering']
            except ValueError:
                # Caso de seguridad por si las entradas salen del universo lógico
                fuzzy_steering = 0.0 
            
            msg.linear.x = v_eff
            msg.angular.z = fuzzy_steering
            
            self.last_error = self.line_error
        else:
            msg.linear.x = 0.0
            msg.angular.z = 0.0

        self.pub.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = FuzzyPuzzlebotController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Cerrando controlador...")
    finally:
        node.destroy_node()
        rclpy.try_shutdown()

if __name__ == '__main__':
    main()