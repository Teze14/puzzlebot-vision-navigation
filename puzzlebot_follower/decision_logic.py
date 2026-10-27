#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32, Bool
from my_interfaces.msg import ColorStatus, SignStatus
from enum import Enum, auto


class State(Enum):
    FOLLOWING           = auto()
    STOP_HOLD           = auto()   # stopped at stop sign, counting down
    ROADWORK_SLOW       = auto()   # reduced speed, normal line following
    GIVE_WAY_APPROACH   = auto()   # slow approach to intersection
    INTERSECTION_APPROACH = auto() # directional sign seen, slowing to intersection
    INTERSECTION_WAIT   = auto()   # at intersection, waiting for green light
    MANEUVER            = auto()   # executing timed open-loop turn / straight


class Direction(Enum):
    NONE        = auto()
    STRAIGHT    = auto()
    LEFT        = auto()
    RIGHT       = auto()
    ROUNDABOUT  = auto()


class PuzzlebotController(Node):
    def __init__(self):
        super().__init__("puzzlebot_decision_logic")

        # Parameters 
        self.declare_parameter("kp", 0.8)
        self.declare_parameter("kd", 0.1)
        self.declare_parameter("max_v", 0.2)
        self.declare_parameter("yellow_speed_factor",   0.4)
        self.declare_parameter("roadwork_speed_factor", 0.5)
        self.declare_parameter("give_way_speed_factor", 0.3)
        self.declare_parameter("approach_speed_factor", 0.4)
        self.declare_parameter("maneuver_linear_v",     0.15)
        self.declare_parameter("maneuver_angular_w",    0.8)
        self.declare_parameter("stop_hold_time",        3.0)
        self.declare_parameter("approach_time",         2.5)
        self.declare_parameter("maneuver_straight_time", 1.5)
        self.declare_parameter("maneuver_turn_time",    3.0)
        self.declare_parameter("sign_confirm_count",    5)
        self.declare_parameter("roadwork_timeout",      3.0)
        self.declare_parameter("sign_cooldown_time",          5.0)
        self.declare_parameter("red_timeout",                 1.5)
        self.declare_parameter("intersection_wait_timeout",  10.0)

        # Pub / Sub
        self.pub            = self.create_publisher(Twist, "/cmd_vel",     10)
        self.line_reset_pub = self.create_publisher(Bool,  "/line_reset",  10)
        self.create_subscription(Float32,     "/line_error",    self.cb_line_error, 10)
        self.create_subscription(ColorStatus, "/color_status",  self.cb_color,      10)
        self.create_subscription(SignStatus,  "/sign_status",   self.cb_sign,       10)
        self.create_subscription(Bool,        "/zebra_detected", self.cb_zebra,     10)

        # Line error state
        self.line_error = 0.0
        self.last_error = 0.0

        # Traffic light state
        self.held_by_red     = False
        self.yellow_detected = False
        self.green_detected  = False
        self._last_red_time  = 0.0

        # Zebra crossing
        self.zebra_detected  = False

        # Sign debounce counters 
        self._sign_keys = ['stop', 'give_way', 'ahead_only',
                           'turn_right', 'turn_left', 'roundabout', 'roadwork']
        self.sign_counters = {k: 0 for k in self._sign_keys}
        self.last_roadwork_time  = 0.0
        self._stop_cooldown_until = 0.0

        #    FSM state 
        self.state             = State.FOLLOWING
        self.latched_direction = Direction.NONE
        self.state_timer       = 0.0   # seconds elapsed in current state

        self.create_timer(0.05, self.control_loop)   # 20 Hz
        self.get_logger().info("Puzzlebot FSM Controller Started")

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def cb_line_error(self, msg):
        self.line_error = msg.data

    def cb_color(self, msg):
        self.yellow_detected = msg.yellow
        self.green_detected  = msg.green
        if msg.red:
            self._last_red_time = self.get_clock().now().nanoseconds / 1e9
            self.held_by_red = True
        elif msg.green:
            self.held_by_red = False

    def cb_zebra(self, msg):
        self.zebra_detected = msg.data

    def cb_sign(self, msg):
        confirm = self.get_parameter("sign_confirm_count").get_parameter_value().integer_value

        detected = {
            'stop':       msg.stop,
            'give_way':   msg.give_way,
            'ahead_only': msg.ahead_only,
            'turn_right': msg.turn_right,
            'turn_left':  msg.turn_left,
            'roundabout': msg.roundabout,
            'roadwork':   msg.roadwork,
        }

        # Hysteresis filter: +1 when seen, -1 when not, clamped to [0, confirm*2]
        for key in self._sign_keys:
            if detected[key]:
                self.sign_counters[key] = min(self.sign_counters[key] + 1, confirm * 2)
            else:
                self.sign_counters[key] = max(self.sign_counters[key] - 1, 0)

        if self.sign_counters['roadwork'] >= confirm:
            self.last_roadwork_time = self.get_clock().now().nanoseconds / 1e9

        # Only allow new sign triggers from FOLLOWING or ROADWORK_SLOW
        if self.state not in (State.FOLLOWING, State.ROADWORK_SLOW):
            return

        # Priority: stop > give_way > directional signs > roadwork
        now = self.get_clock().now().nanoseconds / 1e9
        if self.sign_counters['stop'] >= confirm and now > self._stop_cooldown_until:
            self._reset_counters()
            self._enter_state(State.STOP_HOLD)

        elif self.sign_counters['give_way'] >= confirm and self.zebra_detected:
            self.latched_direction = Direction.STRAIGHT
            self._reset_counters()
            self._enter_state(State.INTERSECTION_APPROACH)

        elif self.sign_counters['turn_left'] >= confirm and self.zebra_detected:
            self.latched_direction = Direction.LEFT
            self._reset_counters()
            self._enter_state(State.INTERSECTION_APPROACH)

        elif self.sign_counters['turn_right'] >= confirm and self.zebra_detected:
            self.latched_direction = Direction.RIGHT
            self._reset_counters()
            self._enter_state(State.INTERSECTION_APPROACH)

        elif self.sign_counters['ahead_only'] >= confirm and self.zebra_detected:
            self.latched_direction = Direction.STRAIGHT
            self._reset_counters()
            self._enter_state(State.INTERSECTION_APPROACH)

        elif self.sign_counters['roundabout'] >= confirm and self.zebra_detected:
            self.latched_direction = Direction.ROUNDABOUT
            self._reset_counters()
            self._enter_state(State.INTERSECTION_APPROACH)

        elif self.sign_counters['roadwork'] >= confirm and self.state == State.FOLLOWING:
            self._enter_state(State.ROADWORK_SLOW)

    # ── FSM helpers ───────────────────────────────────────────────────────────

    def _enter_state(self, new_state):
        prev_state       = self.state
        self.state       = new_state
        self.state_timer = 0.0
        if new_state == State.INTERSECTION_WAIT:
            self.green_detected = False
        if new_state == State.FOLLOWING:
            self._reset_counters()
            if prev_state == State.MANEUVER:
                # Tell the line follower to forget last_cx so it re-acquires
                # from the image centre instead of the pre-maneuver position.
                reset_msg = Bool()
                reset_msg.data = True
                self.line_reset_pub.publish(reset_msg)
        self.get_logger().info(
            f"State → {new_state.name}  |  direction={self.latched_direction.name}")

    def _reset_counters(self):
        self.sign_counters = {k: 0 for k in self._sign_keys}

    def _pd_steering(self, kp, kd):
        derivative      = self.line_error - self.last_error
        self.last_error = self.line_error
        # Negative: line to the right (positive error) → turn right (negative angular.z)
        return ((kp * self.line_error) + (kd * derivative))

    def _line_follow_velocity(self, base_v):
        """Proportional speed reduction with line error (slows in curves)."""
        return base_v * (1.0 - min(abs(self.line_error), 1.0) * 0.9)

    # ── Control loop (FSM) ────────────────────────────────────────────────────

    def control_loop(self):
        DT   = 0.05
        kp   = self.get_parameter("kp").get_parameter_value().double_value
        kd   = self.get_parameter("kd").get_parameter_value().double_value
        max_v = self.get_parameter("max_v").get_parameter_value().double_value

        msg = Twist()

        # Auto-clear red if it hasn't been seen recently (prevents false-positive lockup)
        red_timeout = self.get_parameter("red_timeout").get_parameter_value().double_value
        now = self.get_clock().now().nanoseconds / 1e9
        if self.held_by_red and (now - self._last_red_time) > red_timeout:
            self.held_by_red = False

        # Red light is a cross-cutting stop in every state except MANEUVER
        if self.held_by_red and self.state != State.MANEUVER:
            self.pub.publish(msg)
            return

        # ── FOLLOWING ─────────────────────────────────────────────────────────
        if self.state == State.FOLLOWING:
            confirm = self.get_parameter("sign_confirm_count").get_parameter_value().integer_value
            # Pre-slow as soon as any intersection sign starts accumulating detections.
            # Lower speed helps the camera capture a clearer image for zebra detection.
            intersection_signs = ['turn_left', 'turn_right', 'ahead_only', 'roundabout', 'give_way']
            sign_building = any(self.sign_counters[k] >= max(1, confirm // 2)
                                for k in intersection_signs)
            if self.yellow_detected:
                factor = self.get_parameter("yellow_speed_factor").get_parameter_value().double_value
            elif sign_building:
                factor = self.get_parameter("approach_speed_factor").get_parameter_value().double_value
            else:
                factor = 1.0
            msg.linear.x  = self._line_follow_velocity(max_v * factor)
            msg.angular.z = self._pd_steering(kp, kd)

        # ── STOP_HOLD ─────────────────────────────────────────────────────────
        elif self.state == State.STOP_HOLD:
            self.state_timer += DT
            stop_time = self.get_parameter("stop_hold_time").get_parameter_value().double_value
            if self.state_timer >= stop_time:
                cooldown = self.get_parameter("sign_cooldown_time").get_parameter_value().double_value
                self._stop_cooldown_until = self.get_clock().now().nanoseconds / 1e9 + cooldown
                self._enter_state(State.FOLLOWING)
            # msg is already zero Twist

        # ── ROADWORK_SLOW ─────────────────────────────────────────────────────
        elif self.state == State.ROADWORK_SLOW:
            factor = self.get_parameter("roadwork_speed_factor").get_parameter_value().double_value
            msg.linear.x  = self._line_follow_velocity(max_v * factor)
            msg.angular.z = self._pd_steering(kp, kd)
            timeout = self.get_parameter("roadwork_timeout").get_parameter_value().double_value
            now = self.get_clock().now().nanoseconds / 1e9
            if (now - self.last_roadwork_time) > timeout:
                self._enter_state(State.FOLLOWING)

        # ── GIVE_WAY_APPROACH ─────────────────────────────────────────────────
        elif self.state == State.GIVE_WAY_APPROACH:
            factor = self.get_parameter("give_way_speed_factor").get_parameter_value().double_value
            msg.linear.x  = self._line_follow_velocity(max_v * factor)
            msg.angular.z = self._pd_steering(kp, kd)
            self.state_timer += DT
            approach_time = self.get_parameter("approach_time").get_parameter_value().double_value
            if self.state_timer >= approach_time:
                self._enter_state(State.INTERSECTION_WAIT)

        # ── INTERSECTION_APPROACH ─────────────────────────────────────────────
        # Drive straight at a fixed speed for approach_time seconds, ignoring
        # the line follower. This advances the robot from the zebra detection
        # point to the actual intersection centre before stopping to wait for green.
        elif self.state == State.INTERSECTION_APPROACH:
            factor = self.get_parameter("approach_speed_factor").get_parameter_value().double_value
            msg.linear.x  = max_v * factor
            msg.angular.z = 0.0
            self.state_timer += DT
            approach_time = self.get_parameter("approach_time").get_parameter_value().double_value
            if self.state_timer >= approach_time:
                self._enter_state(State.INTERSECTION_WAIT)

        # ── INTERSECTION_WAIT ─────────────────────────────────────────────────
        elif self.state == State.INTERSECTION_WAIT:
            self.state_timer += DT
            wait_timeout = self.get_parameter("intersection_wait_timeout").get_parameter_value().double_value
            if self.green_detected:
                self._enter_state(State.MANEUVER)
            elif self.state_timer >= wait_timeout:
                # No green after timeout — abort and resume line following
                self.get_logger().warn("INTERSECTION_WAIT timed out, resuming FOLLOWING")
                self.latched_direction = Direction.NONE
                self._enter_state(State.FOLLOWING)

        # ── MANEUVER ──────────────────────────────────────────────────────────
        elif self.state == State.MANEUVER:
            lin_v  = self.get_parameter("maneuver_linear_v").get_parameter_value().double_value
            ang_w  = self.get_parameter("maneuver_angular_w").get_parameter_value().double_value
            t_straight = self.get_parameter("maneuver_straight_time").get_parameter_value().double_value
            t_turn     = self.get_parameter("maneuver_turn_time").get_parameter_value().double_value

            if self.latched_direction in (Direction.STRAIGHT, Direction.NONE):
                msg.linear.x  = lin_v
                msg.angular.z = 0.0
                target_time   = t_straight

            elif self.latched_direction == Direction.LEFT:
                msg.linear.x  = lin_v
                msg.angular.z = ang_w
                target_time   = t_turn

            elif self.latched_direction == Direction.RIGHT:
                msg.linear.x  = lin_v
                msg.angular.z = -ang_w
                target_time   = t_turn

            elif self.latched_direction == Direction.ROUNDABOUT:
                # Slow circular arc — tune angular_w to match the track radius
                msg.linear.x  = lin_v * 0.7
                msg.angular.z = ang_w * 0.5
                target_time   = t_turn

            else:
                target_time = t_straight

            self.state_timer += DT
            if self.state_timer >= target_time:
                self.latched_direction = Direction.NONE
                self._enter_state(State.FOLLOWING)

        self.pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = PuzzlebotController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Shutting down...")
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
