#!/usr/bin/env python3
import rclpy
import cv2
import numpy as np
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import Float32, Bool
from rclpy import qos

# Zebra detection tuning
# Detect the 6 small horizontal rectangles that form the intersection zebra.
# Only thresh (dark rects via BINARY_INV) is scanned — the inverse creates a
# single large connected blob from the light background, adding noise.
ZEBRA_RECT_MIN_AREA   = 150    # px² lower bound (far/small rects)
ZEBRA_RECT_MAX_AREA   = 20000  # px² upper bound (near rects look large due to perspective)
ZEBRA_RECT_MIN_ASPECT = 1.3    # w/h — rects close-up look squarer, so keep threshold low
ZEBRA_RECT_MIN_WIDTH  = 0.05   # fraction of ROI width each rect must span
ZEBRA_MIN_RECTS       = 6      # need ≥3 qualifying rects out of 6
ZEBRA_CONFIRM         = 3      # hysteresis frames needed to latch zebra=True


class LineFollowerVision(Node):
    def __init__(self):
        super().__init__("line_follower_vision")
        self.img = None
        self.last_cx = None
        self._zebra_counter = 0

        # CLAHE instance (created once; reused every frame for efficiency)
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

        self.sub = self.create_subscription(
            CompressedImage,
            "/video_source/compressed",
            self.camera_callback,
            qos.qos_profile_sensor_data)

        self.error_pub  = self.create_publisher(Float32, "/line_error",    10)
        self.zebra_pub  = self.create_publisher(Bool,    "/zebra_detected", 10)
        self.create_subscription(Bool, "/line_reset", self.cb_line_reset, 10)
        self.create_timer(0.05, self.process_image)
        self.get_logger().info("Line Follower Vision Started")

    def camera_callback(self, msg):
        np_arr = np.frombuffer(msg.data, np.uint8)
        self.img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    def cb_line_reset(self, msg):
        if msg.data:
            self.last_cx = None  # re-acquire from image centre on next frame

    def process_image(self):
        if self.img is None:
            return

        frame = self.img.copy()
        height, width, _ = frame.shape

        roi_start = int(height * 0.6)
        roi = frame[roi_start:, :]

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # CLAHE equalises local contrast → Otsu stays reliable under shadows and
        # bright patches that would otherwise collapse the bimodal histogram.
        gray = self._clahe.apply(gray)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        error_to_publish = 0.0
        MIN_AREA = 500
        center_img = width // 2
        valid_contours = [c for c in contours if cv2.contourArea(c) > MIN_AREA]

        if valid_contours:
            candidates = []
            for c in valid_contours:
                M = cv2.moments(c)
                if M['m00'] > 0:
                    cx = int(M['m10'] / M['m00'])
                    candidates.append((cx, c))

            if candidates:
                ref_x = self.last_cx if self.last_cx is not None else center_img
                cx, best_contour = min(candidates, key=lambda item: abs(item[0] - ref_x))

                MAX_JUMP = int(width * 0.20)
                if self.last_cx is not None and abs(cx - self.last_cx) > MAX_JUMP:
                    cx = self.last_cx + int(np.sign(cx - self.last_cx) * MAX_JUMP)

                self.last_cx = cx
                error_to_publish = float(cx - center_img) / (width / 2)

                cv2.drawContours(roi, [best_contour], -1, (0, 255, 0), 2)
                cv2.circle(roi, (cx, roi.shape[0] // 2), 7, (0, 0, 255), -1)

        msg = Float32()
        msg.data = error_to_publish
        self.error_pub.publish(msg)

        # ── Zebra crossing detection ──────────────────────────────────────────
        # Scan only thresh (BINARY_INV makes dark zebra stripes white).
        # The bitwise-not is skipped: it turns the large light background into one
        # giant connected blob that swamps the real stripe contours.
        rect_count = 0
        min_w = int(width * ZEBRA_RECT_MIN_WIDTH)
        cnts_z, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in cnts_z:
            area = cv2.contourArea(c)
            if area < ZEBRA_RECT_MIN_AREA or area > ZEBRA_RECT_MAX_AREA:
                continue
            x, y, w, h = cv2.boundingRect(c)
            aspect = w / max(h, 1)
            passes = aspect >= ZEBRA_RECT_MIN_ASPECT and w >= min_w
            # Diagnostic: draw every size-passing candidate; green=pass, red=fail
            dbg_color = (0, 255, 0) if passes else (0, 0, 255)
            cv2.rectangle(roi, (x, y), (x + w, y + h), dbg_color, 1)
            cv2.putText(roi, f"{int(area)} {aspect:.1f}", (x, max(y - 2, 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.30, dbg_color, 1)
            if passes:
                rect_count += 1

        if rect_count >= ZEBRA_MIN_RECTS:
            self._zebra_counter = min(self._zebra_counter + 1, ZEBRA_CONFIRM * 2)
        else:
            self._zebra_counter = max(self._zebra_counter - 1, 0)

        zebra_detected = self._zebra_counter >= ZEBRA_CONFIRM
        zebra_msg = Bool()
        zebra_msg.data = zebra_detected
        self.zebra_pub.publish(zebra_msg)

        z_color = (0, 255, 0) if zebra_detected else (0, 0, 255)
        cv2.putText(roi, f"ZEBRA: {'YES' if zebra_detected else 'NO'} (rects={rect_count})",
                    (5, roi.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.50, z_color, 2)

        cv2.imshow("Line Mask", thresh)
        cv2.imshow("Line Detection", roi)
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
