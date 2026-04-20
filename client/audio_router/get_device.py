"""
client/audio_router/get_device.py
Liệt kê thiết bị audio cho người dùng chọn
"""

import sounddevice as sd
import platform


def _find_device(name)

def list_devices():
    """In ra danh sách thiết bị audio cho người dùng chọn"""
    print("\n[AUDIO] Danh sách thiết bị audio:")
    print(sd.query_devices())

if __name__ == "__main__":
    list_devices()