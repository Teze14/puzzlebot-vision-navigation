#!/usr/bin/env python3
import threading
import rclpy
import cv2
import numpy as np
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from my_interfaces.msg import ColorStatus, SignStatus
from rclpy import qos

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

LIGHT_MAP = {'red': 'red', 'yellow': 'yellow', 'green': 'green'}
SIGN_MAP  = {
    'stop':             'stop',
    'give_way':         'give_way',
    'flecha_derecha':   'turn_right',
    'flecha_izquierda': 'turn_left',
    'flecha_derecho':   'ahead_only',
    'zona_obras':       'roadwork',
    'glorieta':         'roundabout',
}


class CnnDetectorNode(Node):
    def __init__(self):
        super().__init__("cnn_detector")

        self.declare_parameter("model_path", "")
        self.declare_parameter("confidence_threshold", 0.75)

        # Cache threshold — avoids slow get_parameter() on every inference call
        self._threshold = self.get_parameter("confidence_threshold").get_parameter_value().double_value

        self.model = None
        self._img_lock = threading.Lock()
        self._latest_img = None

        self.color_pub = self.create_publisher(ColorStatus, "/color_status", 10)
        self.sign_pub  = self.create_publisher(SignStatus,  "/sign_status",  10)

        self.create_subscription(
            CompressedImage, "/video_source/compressed",
            self.camera_callback,
            qos.qos_profile_sensor_data)

        self._load_model()

        # Inference runs in its own thread — never blocks the ROS executor
        self._running = True
        self._inf_thread = threading.Thread(target=self._inference_loop, daemon=True)
        self._inf_thread.start()

        self.get_logger().info("CNN Detector (YOLOv8) started")

    def _load_model(self):
        if not YOLO_AVAILABLE:
            self.get_logger().error("ultralytics is not installed.")
            return

        path = self.get_parameter("model_path").get_parameter_value().string_value
        if not path:
            self.get_logger().warn("model_path is empty — set it in params.yaml.")
            return

        try:
            self.model = YOLO(path)
            self.get_logger().info(f"Classes: {self.model.names}")
            # Warm-up: triggers JIT compilation before the robot moves
            dummy = np.zeros((480, 640, 3), dtype=np.uint8)
            self.model(dummy, verbose=False)
            self.get_logger().info("Model warm-up complete — ready to detect")
        except Exception as e:
            self.get_logger().error(f"Failed to load model: {e}")

    def camera_callback(self, msg):
        np_arr = np.frombuffer(msg.data, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        with self._img_lock:
            self._latest_img = img

    def _inference_loop(self):
        while self._running and rclpy.ok():
            with self._img_lock:
                img = self._latest_img

            color_msg = ColorStatus()
            sign_msg  = SignStatus()

            if img is None or self.model is None:
                # No frame yet — publish empty messages so subscribers don't stall
                self.color_pub.publish(color_msg)
                self.sign_pub.publish(sign_msg)
                threading.Event().wait(0.05)
                continue

            height = img.shape[0]
            roi_end = int(height * 0.6)
            roi = img[:roi_end, :].copy()

            # Draw ROI boundary on the full frame for reference
            vis = img.copy()
            cv2.line(vis, (0, roi_end), (vis.shape[1], roi_end), (0, 255, 255), 2)
            cv2.putText(vis, "ROI", (5, roi_end - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            try:
                results = self.model(roi, verbose=False, conf=self._threshold)

                # Track best detection per category independently
                best_light = (0.0, None)
                best_sign  = (0.0, None)

                for r in results:
                    for box in r.boxes:
                        conf  = float(box.conf[0])
                        label = self.model.names[int(box.cls[0])]

                        # Draw every detected box on the ROI visualization
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        color = (255, 100, 0) if label in LIGHT_MAP else (0, 180, 255)
                        cv2.rectangle(roi, (x1, y1), (x2, y2), color, 2)
                        cv2.putText(roi, f"{label} {conf:.2f}",
                                    (x1, max(y1 - 6, 10)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

                        if label in LIGHT_MAP and conf > best_light[0]:
                            best_light = (conf, label)
                        elif label in SIGN_MAP and conf > best_sign[0]:
                            best_sign = (conf, label)

                if best_light[1] is not None:
                    setattr(color_msg, LIGHT_MAP[best_light[1]], True)
                    self.get_logger().info(
                        f"Light: {best_light[1]} ({best_light[0]:.2f})")

                if best_sign[1] is not None:
                    setattr(sign_msg, SIGN_MAP[best_sign[1]], True)
                    self.get_logger().info(
                        f"Sign: {best_sign[1]} ({best_sign[0]:.2f})")

            except Exception as e:
                self.get_logger().error(f"Inference error: {e}")

            # Overlay the annotated ROI back onto the full-frame view
            vis[:roi_end, :] = roi
            cv2.imshow("CNN Detections", vis)
            cv2.waitKey(1)

            self.color_pub.publish(color_msg)
            self.sign_pub.publish(sign_msg)

    def destroy_node(self):
        self._running = False
        cv2.destroyAllWindows()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CnnDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
