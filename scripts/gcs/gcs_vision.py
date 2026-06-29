"""
scripts/gcs/gcs_vision.py
Computer Vision module: YOLOv8 + ByteTrack + PID Controller.

Chạy độc lập (test webcam, không cần DroneKit):
    python gcs_vision.py --standalone --source 0

Chạy như một module trong hệ thống GCS đầy đủ:
    Được import bởi gcs_main.py
"""

import argparse
import logging
import time
import cv2
import numpy as np

from ultralytics import YOLO

logger = logging.getLogger("gcs_vision")

_R = "\033[91m"
_G = "\033[92m"
_Y = "\033[93m"
_C = "\033[96m"
_W = "\033[97m"
_RST = "\033[0m"


def vision_tracking_loop(state, controller, video_source=1):
    """
    Luồng camera chạy YOLOv8, ByteTrack và tính toán PID độc lập.
    Tương thích với cả GPU (CUDA) và CPU.
    Được gọi từ gcs_main.py như một daemon thread.

    Args:
        state: DroneState object (trạng thái chia sẻ)
        controller: UAVController object
        video_source: ID camera hoặc đường dẫn file video
    """
    _run_tracking(state, controller, video_source, standalone=False)


def _run_tracking(state, controller, video_source=0, standalone=False):
    """Core tracking loop — dùng cho cả standalone mode và integrated mode."""
    from gcs_flight_controller import PIDController

    logger.info("📷 Khởi động luồng Computer Vision (YOLOv8 Medium + ByteTrack)...")

    model = _load_yolo_model()
    if model is None:
        logger.error("❌ Không thể tải YOLOv8. Luồng Vision dừng lại.")
        return

    cap = _open_camera(video_source)
    if cap is None:
        logger.error("❌ Mất tín hiệu Video. Luồng Vision tạm dừng.")
        return

    dt = 0.05
    pid_yaw      = PIDController(Kp=0.35, Ki=0.00, Kd=0.05, dt=dt)
    pid_throttle = PIDController(Kp=0.40, Ki=0.02, Kd=0.08, dt=dt)
    pid_pitch    = PIDController(Kp=0.30, Ki=0.01, Kd=0.06, dt=dt)

    REF_WIDTH, REF_HEIGHT = 640, 480
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, REF_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, REF_HEIGHT)

    CONFIDENCE_THRESHOLD = 0.50

    fps_counter = FPSCounter(window=30)

    logger.info(f"✅ Vision & PID sẵn sàng. Confidence threshold: {CONFIDENCE_THRESHOLD:.0%}")
    if standalone:
        logger.info(f"{_Y}[STANDALONE MODE]{_RST} Nhấn 'q' để thoát, 'f' để bật Follow simulation.")

    target_class = "person"
    is_tracking_sim = False

    while True:
        if not cap.isOpened():
            time.sleep(1)
            continue

        ret, frame = cap.read()
        if not ret:
            time.sleep(0.05)
            continue

        fps_counter.tick()

        if standalone:
            should_track = is_tracking_sim
            target_cls = target_class
            vehicle_ok = True
        else:
            should_track = state.is_tracking
            target_cls = state.target_class if hasattr(state, "target_class") else "person"
            vehicle_ok = controller.vehicle is not None

        if not should_track or not vehicle_ok:
            _draw_idle_overlay(frame, fps_counter.fps, standalone, is_tracking_sim if standalone else False)
            cv2.imshow("GCS Vision Tracking", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if standalone and key == ord("f"):
                is_tracking_sim = not is_tracking_sim
                logger.info(f"Toggle tracking: {'ON' if is_tracking_sim else 'OFF'}")
            pid_yaw.reset()
            pid_throttle.reset()
            pid_pitch.reset()
            time.sleep(0.05)
            continue

        results = model.track(
            frame,
            tracker="bytetrack.yaml",
            persist=True,
            verbose=False,
            conf=CONFIDENCE_THRESHOLD,
        )

        target_found = False
        velocity_yaw_rate = 0.0
        velocity_z = 0.0
        velocity_x = 0.0
        error_x = 0.0
        error_y = 0.0

        if results and len(results) > 0 and results[0].boxes is not None:
            boxes = results[0].boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = model.names[cls_id]
                conf = float(box.conf[0])

                if cls_name == target_cls and conf >= CONFIDENCE_THRESHOLD:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    cx = (x1 + x2) / 2.0
                    cy = (y1 + y2) / 2.0
                    bbox_h = y2 - y1

                    error_x = cx - (REF_WIDTH / 2.0)
                    error_y = cy - (REF_HEIGHT / 2.0)

                    ref_bbox_h = 200.0
                    error_z = ref_bbox_h - bbox_h

                    if bbox_h > 250:
                        pid_pitch.Kp = 0.15
                    elif bbox_h < 100:
                        pid_pitch.Kp = 0.45
                    else:
                        pid_pitch.Kp = 0.30

                    raw_yaw = pid_yaw.compute(error_x)
                    velocity_yaw_rate = np.clip(raw_yaw / 100.0, -0.5, 0.5)

                    raw_z = pid_throttle.compute(error_y)
                    velocity_z = np.clip(raw_z / 100.0, -1.0, 1.0)

                    raw_x = pid_pitch.compute(error_z)
                    velocity_x = np.clip(raw_x / 100.0, -1.0, 1.0)

                    target_found = True

                    _draw_tracking_overlay(
                        frame, x1, y1, x2, y2, cx, cy,
                        cls_name, conf, error_x, error_y,
                        velocity_yaw_rate, velocity_z, velocity_x,
                        REF_WIDTH, REF_HEIGHT
                    )
                    break

        failsafe_ok = True
        if not standalone:
            failsafe_ok = not state.failsafe_triggered

        if target_found and failsafe_ok:
            if not standalone:
                controller.send_continuous_velocity_and_yaw(
                    vx=velocity_x,
                    vy=0,
                    vz=velocity_z,
                    yaw_rate=velocity_yaw_rate,
                )
            logger.debug(
                f"PID → yaw_rate={velocity_yaw_rate:+.3f} vz={velocity_z:+.3f} vx={velocity_x:+.3f} "
                f"| err_x={error_x:+.1f} err_y={error_y:+.1f}"
            )
        else:
            if not standalone and vehicle_ok:
                controller.send_continuous_velocity_and_yaw(0, 0, 0, 0)
            pid_yaw.reset()
            pid_throttle.reset()
            pid_pitch.reset()

        _draw_fps(frame, fps_counter.fps)

        current_fps = fps_counter.fps if fps_counter.fps > 0 else 20
        if fps_counter.frame_count % max(1, int(current_fps * 2)) == 0:
            status = "🎯 TRACKING" if target_found else "👁️  SCANNING"
            color = _G if target_found else _Y
            print(
                f"\r{color}{status}{_RST} | FPS: {fps_counter.fps:.1f} "
                f"| err_x={error_x:+5.1f} err_y={error_y:+5.1f} "
                f"| yaw={velocity_yaw_rate:+.3f} vz={velocity_z:+.3f} vx={velocity_x:+.3f}  ",
                end="", flush=True
            )

        cv2.imshow("GCS Vision Tracking", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            logger.info("Nhấn 'q' — Dừng luồng Vision.")
            break
        if standalone and key == ord("f"):
            is_tracking_sim = not is_tracking_sim
            logger.info(f"[STANDALONE] Follow mode: {'ON' if is_tracking_sim else 'OFF'}")

    cap.release()
    cv2.destroyAllWindows()
    print()
    logger.info("📷 Luồng Vision đã dừng.")



def _load_yolo_model():
    """Load YOLOv8 lên GPU hoặc fallback sang CPU."""
    try:
        model = YOLO("yolov8m.pt")
        model.to("cuda")
        logger.info("✅ Đã load YOLOv8 Medium lên GPU (CUDA)!")
        return model
    except Exception as e:
        logger.warning(f"⚠️  Không thể dùng GPU: {e}")
        logger.info("🔄 Thử lại bằng CPU...")
        try:
            model = YOLO("yolov8m.pt")
            model.to("cpu")
            logger.info("✅ Đã load YOLOv8 Medium lên CPU!")
            return model
        except Exception as e2:
            logger.error(f"❌ Không thể tải model YOLOv8: {e2}")
            return None


def _open_camera(video_source):
    """Mở camera theo source ID, fallback sang webcam mặc định (0)."""
    cap = cv2.VideoCapture(video_source)
    if cap.isOpened():
        logger.info(f"✅ Đã mở camera source {video_source}.")
        return cap
    logger.warning(f"⚠️  Không thể mở source {video_source}. Thử webcam mặc định (0)...")
    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        logger.info("✅ Đã mở webcam mặc định (source 0).")
        return cap
    return None


def _draw_tracking_overlay(frame, x1, y1, x2, y2, cx, cy,
                            cls_name, conf, error_x, error_y,
                            yaw_rate, vz, vx, frame_w, frame_h):
    """Vẽ bounding box, crosshair, PID error bar lên frame."""
    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
    cx, cy = int(cx), int(cy)
    center_x, center_y = frame_w // 2, frame_h // 2

    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 80), 2)

    label = f"{cls_name} {conf:.0%}"
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
    cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), (0, 200, 60), -1)
    cv2.putText(frame, label, (x1 + 2, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

    cv2.line(frame, (center_x - 20, center_y), (center_x + 20, center_y), (255, 255, 255), 1)
    cv2.line(frame, (center_x, center_y - 20), (center_x, center_y + 20), (255, 255, 255), 1)

    error_color = (0, 140, 255)
    cv2.arrowedLine(frame, (center_x, center_y), (cx, cy), error_color, 2, tipLength=0.15)

    _draw_pid_bars(frame, error_x, error_y, yaw_rate, vz, vx, frame_w, frame_h)


def _draw_pid_bars(frame, error_x, error_y, yaw_rate, vz, vx, frame_w, frame_h):
    """Vẽ PID status bars ở góc dưới phải."""
    bar_x = frame_w - 140
    bar_y = frame_h - 90
    bar_w = 100
    bar_h = 8
    gap = 18

    params = [
        ("YAW", yaw_rate, (-0.5, 0.5), (80, 200, 255)),
        ("VZ ", vz,       (-1.0, 1.0), (255, 200, 80)),
        ("VX ", vx,       (-1.0, 1.0), (80, 255, 180)),
    ]
    for i, (label, val, (vmin, vmax), color) in enumerate(params):
        y = bar_y + i * gap
        cv2.rectangle(frame, (bar_x, y), (bar_x + bar_w, y + bar_h), (50, 50, 50), -1)
        norm = (val - vmin) / (vmax - vmin)
        fill = int(norm * bar_w)
        mid = bar_w // 2
        if fill > mid:
            cv2.rectangle(frame, (bar_x + mid, y), (bar_x + fill, y + bar_h), color, -1)
        else:
            cv2.rectangle(frame, (bar_x + fill, y), (bar_x + mid, y + bar_h), color, -1)
        cv2.line(frame, (bar_x + mid, y - 1), (bar_x + mid, y + bar_h + 1), (200, 200, 200), 1)
        cv2.putText(frame, f"{label}:{val:+.2f}", (bar_x - 5, y + 7),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (220, 220, 220), 1)


def _draw_idle_overlay(frame, fps, standalone, sim_tracking):
    """Vẽ overlay khi không tracking."""
    h, w = frame.shape[:2]
    cx, cy = w // 2, h // 2
    cv2.line(frame, (cx - 25, cy), (cx + 25, cy), (100, 100, 100), 1)
    cv2.line(frame, (cx, cy - 25), (cx, cy + 25), (100, 100, 100), 1)

    if standalone:
        status = "FOLLOW: ON (sim)" if sim_tracking else "FOLLOW: OFF — Nhấn 'F'"
        color = (0, 220, 100) if sim_tracking else (0, 150, 255)
        cv2.putText(frame, status, (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        cv2.putText(frame, "[STANDALONE MODE]", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)

    _draw_fps(frame, fps)


def _draw_fps(frame, fps):
    """Vẽ FPS counter ở góc trên phải."""
    h, w = frame.shape[:2]
    color = (0, 255, 80) if fps >= 15 else (0, 140, 255) if fps >= 8 else (0, 60, 255)
    cv2.putText(frame, f"FPS: {fps:.1f}", (w - 90, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)


class FPSCounter:
    """Tính FPS theo cửa sổ trượt."""
    def __init__(self, window=30):
        self.window = window
        self.timestamps = []
        self.fps = 0.0
        self.frame_count = 0

    def tick(self):
        now = time.perf_counter()
        self.timestamps.append(now)
        self.frame_count += 1
        if len(self.timestamps) > self.window:
            self.timestamps.pop(0)
        if len(self.timestamps) >= 2:
            elapsed = self.timestamps[-1] - self.timestamps[0]
            self.fps = (len(self.timestamps) - 1) / elapsed if elapsed > 0 else 0.0



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="GCS Vision — Standalone Test Mode")
    parser.add_argument("--standalone", action="store_true", default=True,
                        help="Chạy độc lập (không cần DroneKit/MAVLink)")
    parser.add_argument("--source", default=0, type=int,
                        help="Camera source ID (mặc định: 0)")
    parser.add_argument("--target", default="person",
                        help="Class mục tiêu cần theo dõi (mặc định: person)")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════╗
║        GCS Vision — Standalone Test Mode             ║
╠══════════════════════════════════════════════════════╣
║  Camera source : {args.source:<35}║
║  Target class  : {args.target:<35}║
╠══════════════════════════════════════════════════════╣
║  [Q] Thoát    [F] Toggle Follow Simulation           ║
╚══════════════════════════════════════════════════════╝
""")

    class MockState:
        is_tracking = False
        target_class = args.target
        failsafe_triggered = False

    class MockController:
        vehicle = "mock"
        def send_continuous_velocity_and_yaw(self, *a, **kw): pass

    _run_tracking(MockState(), MockController(), video_source=args.source, standalone=True)
