import logging
import sys
import time
import threading
from collections import deque

from dronekit import connect, VehicleMode

logger = logging.getLogger("gcs_flight_controller")


class DroneState:
    """Quản lý trạng thái chia sẻ giữa GCS Main (nhận lệnh) và Vision (điều khiển)."""
    def __init__(self):
        self.is_tracking = False
        self.target_class = "person"
        self.target_color = None
        self.command_queue = deque()
        self.last_heartbeat_time = time.time()
        self.last_command_time = 0.0
        self.failsafe_triggered = False


class PIDController:
    """
    Bộ điều khiển PID rời rạc (Discrete PID) theo Ziegler-Nichols.
    Có Integral Wind-up Protection và method reset() để tránh drift.
    """
    INTEGRAL_MAX = 50.0

    def __init__(self, Kp, Ki, Kd, dt=0.05):
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.dt = dt
        self.integral = 0.0
        self.prev_error = 0.0

    def compute(self, error: float) -> float:
        """Tính toán output PID với anti-windup."""
        self.integral += error * self.dt
        self.integral = max(-self.INTEGRAL_MAX, min(self.INTEGRAL_MAX, self.integral))
        derivative = (error - self.prev_error) / self.dt
        output = (self.Kp * error) + (self.Ki * self.integral) + (self.Kd * derivative)
        self.prev_error = error
        return output

    def reset(self):
        """Reset trạng thái PID — gọi khi mất mục tiêu hoặc đổi chế độ."""
        self.integral = 0.0
        self.prev_error = 0.0


class UAVController:
    def __init__(self, connection_string: str, baud: int):
        self.connection_string = connection_string
        self.baud = baud
        self.vehicle = None
        self.target_altitude = 2.0
        self._failsafe_thread = None

    def connect_vehicle(self, state: DroneState):
        logger.info(f"Đang kết nối tới UAV tại {self.connection_string} (Baud: {self.baud})...")
        try:
            self.vehicle = connect(self.connection_string, wait_ready=True, baud=self.baud)
            logger.info("✅ Kết nối UAV (MAVLink) thành công!")
            
            self._failsafe_thread = threading.Thread(target=self._failsafe_monitor, args=(state,), daemon=True)
            self._failsafe_thread.start()
            
            @self.vehicle.on_message('*')
            def listener(vehicle, name, message):
                state.last_heartbeat_time = time.time()
                
        except Exception as e:
            logger.error(f"❌ Không thể kết nối UAV: {e}")
            sys.exit(1)

    def _failsafe_monitor(self, state: DroneState):
        """Giám sát tín hiệu Telemetry. Nếu mất sóng quá 3s -> RTL/LOITER."""
        logger.info("🛡️ Failsafe Monitor đã khởi động.")
        while True:
            if self.vehicle and self.vehicle.armed:
                time_since_last_beat = time.time() - state.last_heartbeat_time
                if time_since_last_beat > 3.0 and not state.failsafe_triggered:
                    logger.error(f"🚨 [FAILSAFE] Mất kết nối Telemetry ({time_since_last_beat:.1f}s)! Ép chuyển sang RTL/LOITER.")
                    state.failsafe_triggered = True
                    state.is_tracking = False
                    
                    try:
                        self.vehicle.mode = VehicleMode("RTL")
                    except Exception as e:
                        logger.error(f"Lỗi kích hoạt RTL: {e}")
                
                elif time_since_last_beat < 1.0 and state.failsafe_triggered:
                    logger.info("✅ [FAILSAFE] Đã kết nối lại Telemetry!")
                    state.failsafe_triggered = False

            time.sleep(0.5)

    def execute_command(self, intent: str, entities: dict, state: DroneState) -> str:
        """
        Map các intent (NLP) sang lệnh điều khiển DroneKit.

        Returns:
            str: Mô tả kết quả thực thi để GCS log và gửi về App.
        """
        if not self.vehicle:
            logger.warning("UAV chưa kết nối. Bỏ qua lệnh.")
            return "⚠️ UAV chưa kết nối"

        if "distance_cm" in entities and entities["distance_cm"] > 500:
            logger.warning(f"⚠️ [SAFETY] Vượt quá khoảng cách an toàn! Giảm từ {entities['distance_cm']} xuống 500cm.")
            entities["distance_cm"] = 500

        if "angle_deg" in entities and entities["angle_deg"] > 360:
            logger.warning(f"⚠️ [SAFETY] Vượt quá góc quay an toàn! Giảm từ {entities['angle_deg']} xuống 360 độ.")
            entities["angle_deg"] = 360

        distance_m = entities.get("distance_cm", 100) / 100.0
        angle_deg = entities.get("angle_deg", 90)

        logger.info(f"Thực thi lệnh: {intent} | Tham số: {entities}")

        if state.is_tracking and intent not in ["follow_target", "get_battery", "get_altitude"]:
            logger.info("🛑 Hủy chế độ tự động bám đuổi để thực thi lệnh thủ công.")
            state.is_tracking = False

        if intent == "take_off":
            target_alt = distance_m if "distance_cm" in entities else self.target_altitude
            target_alt = min(target_alt, 3.0)
            self._arm_and_takeoff(target_alt)
            return f"🛫 Cất cánh lên {target_alt:.1f}m"
        elif intent == "land":
            self.vehicle.mode = VehicleMode("LAND")
            return "🛬 Đang hạ cánh"
        elif intent == "return_home":
            self.vehicle.mode = VehicleMode("RTL")
            return "🏠 Đang trở về Home"
        elif intent == "emergency_stop":
            state.is_tracking = False
            self.vehicle.mode = VehicleMode("LOITER")
            logger.warning("🚨 EMERGENCY STOP kích hoạt!")
            return "🚨 EMERGENCY STOP — Drone đang Loiter"
        elif intent in ["hover", "stop"]:
            state.is_tracking = False
            self.vehicle.mode = VehicleMode("LOITER")
            return "✋ Drone đang giữ vị trí (Loiter)"
        elif intent == "follow_target":
            target_cls = entities.get("class", "person")
            state.target_class = target_cls
            state.is_tracking = True
            logger.info(f"🎯 Bật chế độ bám đuổi mục tiêu: {target_cls}")
            return f"🎯 Đang bám đuổi: {target_cls}"
        elif intent == "move_forward":
            self._send_ned_velocity(distance_m, 0, 0, duration=2)
            return f"➡️ Tiến {distance_m:.1f}m"
        elif intent == "move_backward":
            self._send_ned_velocity(-distance_m, 0, 0, duration=2)
            return f"⬅️ Lùi {distance_m:.1f}m"
        elif intent == "move_left":
            self._send_ned_velocity(0, -distance_m, 0, duration=2)
            return f"\u2B05\uFE0F Left {distance_m:.1f}m"
        elif intent == "move_right":
            self._send_ned_velocity(0, distance_m, 0, duration=2)
            return f"\u27A1\uFE0F Right {distance_m:.1f}m"
        elif intent == "ascend":
            current_alt = self.vehicle.location.global_relative_frame.alt if self.vehicle.location.global_relative_frame else 0
            if current_alt + distance_m > 15.0:
                logger.warning("⚠️ [GEOFENCE] Trần bay tối đa là 15m. Hủy lệnh ascend.")
                return f"⚠️ Từ chối lệnh: Vượt trần bay 15m (hiện tại: {current_alt:.1f}m)"
            self._send_ned_velocity(0, 0, -distance_m, duration=2)
            return f"⬆️ Lên cao {distance_m:.1f}m"
        elif intent == "descend":
            self._send_ned_velocity(0, 0, distance_m, duration=2)
            return f"⬇️ Hạ xuống {distance_m:.1f}m"
        elif intent == "rotate_left":
            self._condition_yaw(angle_deg, relative=True, direction=-1)
            return f"↺ Xoay trái {angle_deg}°"
        elif intent == "rotate_right":
            self._condition_yaw(angle_deg, relative=True, direction=1)
            return f"↻ Xoay phải {angle_deg}°"
        elif intent == "get_battery":
            bat = self.vehicle.battery
            msg = f"🔋 Pin: {bat.voltage:.2f}V — {bat.level}%"
            logger.info(msg)
            return msg
        elif intent == "get_altitude":
            alt = self.vehicle.location.global_relative_frame.alt
            msg = f"⛰️ Độ cao hiện tại: {alt:.1f}m"
            logger.info(msg)
            return msg
        else:
            logger.warning(f"Lệnh chưa được hỗ trợ: {intent}")
            return f"❓ Lệnh không nhận diện được: {intent}"


    def _arm_and_takeoff(self, aTargetAltitude):
        logger.info("Basic pre-arm checks")
        if not self.vehicle.is_armable:
            logger.error("UAV chưa sẵn sàng để arm.")
            return

        logger.info("Chuyển mode GUIDED, arming motors")
        self.vehicle.mode = VehicleMode("GUIDED")
        self.vehicle.armed = True

        while not self.vehicle.armed:
            logger.info(" Chờ arming...")
            time.sleep(1)

        logger.info(f"Cất cánh tới độ cao {aTargetAltitude}m!")
        self.vehicle.simple_takeoff(aTargetAltitude)

    def _send_ned_velocity(self, velocity_x, velocity_y, velocity_z, duration):
        from pymavlink import mavutil
        msg = self.vehicle.message_factory.set_position_target_local_ned_encode(
            0, 0, 0, mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED,
            0b0000111111000111, 0, 0, 0,
            velocity_x, velocity_y, velocity_z,
            0, 0, 0, 0, 0
        )
        self.vehicle.send_mavlink(msg)
        time.sleep(duration)
        msg = self.vehicle.message_factory.set_position_target_local_ned_encode(
            0, 0, 0, mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED,
            0b0000111111000111, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0
        )
        self.vehicle.send_mavlink(msg)

    def send_continuous_velocity_and_yaw(self, vx, vy, vz, yaw_rate):
        from pymavlink import mavutil
        type_mask = 0b0000010111000111
        msg = self.vehicle.message_factory.set_position_target_local_ned_encode(
            0, 0, 0, mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED,
            type_mask, 0, 0, 0,
            vx, vy, vz, 0, 0, 0, 0, yaw_rate
        )
        self.vehicle.send_mavlink(msg)

    def _condition_yaw(self, heading, relative=False, direction=1):
        from pymavlink import mavutil
        is_relative = 1 if relative else 0
        msg = self.vehicle.message_factory.command_long_encode(
            0, 0, mavutil.mavlink.MAV_CMD_CONDITION_YAW, 0,
            heading, 0, direction, is_relative, 0, 0, 0
        )
        self.vehicle.send_mavlink(msg)

def command_executor_loop(state: DroneState, controller: UAVController):
    """Liên tục đọc hàng đợi lệnh và thực thi tuần tự."""
    logger.info("⚙️ Khởi động luồng Command Executor...")
    while True:
        if state.command_queue:
            cmd = state.command_queue.popleft()
            intent = cmd.get("intent")
            entities = cmd.get("entities", {})
            result = controller.execute_command(intent, entities, state)
            if result:
                logger.info(f"✅ Kết quả: {result}")
        else:
            time.sleep(0.1)
