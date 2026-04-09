"""
client/audio_router/audio_manager.py
VB-Audio Virtual Cable routing - Optimized for Real-time Speech-to-Text.

Inbound:  Virtual Speaker (Meet Audio Out) → InboundAudioManager
            → Silero VAD → Spectral Subtraction → Normalize → Whisper
Playback: Receive TTS WAV from server → decode → non-blocking play to Real Headphone

Lưu ý: Outbound (microphone) đã được tách sang OutboundAudioManager riêng.
        File này chỉ quản lý Inbound + Playback.
"""
import base64
import io
import logging
import os
import threading
import wave
import queue
import time
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

# Import InboundAudioManager — pipeline đầy đủ cho Virtual Cable
from .inbound import InboundAudioManager

logger = logging.getLogger("paraline.audio")

SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))


class AudioManager:
    """
    Lớp điều phối âm thanh cấp cao.

    Trách nhiệm:
      - Khởi động / dừng InboundAudioManager (thu + xử lý từ Virtual Cable)
      - Quản lý Playback stream (phát TTS ra loa)

    Không xử lý audio trực tiếp — toàn bộ logic nằm trong InboundAudioManager.
    """

    def __init__(self):
        self._running = False

        # Delegate inbound sang InboundAudioManager
        self._inbound = InboundAudioManager()

        # Playback
        self._playback_q      = queue.Queue(maxsize=0)   # vô hạn — không bao giờ drop TTS
        self._playback_buffer = np.zeros(0, dtype=np.float32)
        self._playback_lock   = threading.Lock()

        self._playback_stream: Optional[sd.OutputStream] = None
        self._playback_thread: Optional[threading.Thread] = None

    # ─────────────────────────────────────────────
    # Start / Stop
    # ─────────────────────────────────────────────

    def start(self, inbound_cb: Callable[[str], None], inbound_device: Optional[str] = None):
        """
        Khởi động toàn bộ pipeline.
        inbound_cb(b64_audio): gọi mỗi khi có câu hoàn chỉnh từ Meet.
        inbound_device: tên thiết bị input (override VIRTUAL_SPEAKER_NAME trong .env).
        """
        self._running = True

        out_device_idx = sd.default.device[1]
        print(f"\n[AUDIO] Khởi động AudioManager...")
        print(f"[AUDIO] Playback device: Loa mặc định [idx: {out_device_idx}]\n")

        # ── Khởi động InboundAudioManager ────────────────────
        self._inbound.start(callback=inbound_cb, device_name=inbound_device)

        # ── Playback stream (non-blocking) ───────────────────
        if out_device_idx is not None and out_device_idx >= 0:
            self._playback_stream = sd.OutputStream(
                device=out_device_idx,
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=self._playback_stream_cb,
            )
            self._playback_stream.start()
            logger.info(f"[AUDIO] Playback stream started: device [{out_device_idx}]")
        else:
            logger.error("[AUDIO] Không tìm thấy output device — Playback bị tắt")

        # ── Playback decoder worker ───────────────────────────
        self._playback_thread = threading.Thread(
            target=self._playback_worker,
            name="PlaybackDecoder",
            daemon=True,
        )
        self._playback_thread.start()

        logger.info("[AUDIO] AudioManager started")

    def stop(self):
        self._running = False

        # Dừng inbound
        self._inbound.stop()

        # Dừng playback stream
        if self._playback_stream:
            self._playback_stream.stop()
            self._playback_stream.close()
            self._playback_stream = None

        # Xoá playback buffer
        with self._playback_lock:
            self._playback_buffer = np.zeros(0, dtype=np.float32)

        logger.info("[AUDIO] AudioManager stopped")

    # ─────────────────────────────────────────────
    # Playback API
    # ─────────────────────────────────────────────

    def play_tts(self, audio_b64: str):
        """
        Nhận TTS audio (base64 WAV) từ server và đưa vào hàng đợi phát.
        Non-blocking — trả về ngay lập tức.
        """
        self._playback_q.put_nowait(audio_b64)

    # ─────────────────────────────────────────────
    # Playback Stream Callback — hardware level
    # ─────────────────────────────────────────────

    def _playback_stream_cb(self, outdata, frames, time_info, status):
        """
        Callback của sounddevice — gọi liên tục bởi hardware.
        Chỉ kéo dữ liệu từ buffer ra loa, không làm gì khác.
        """
        with self._playback_lock:
            available = len(self._playback_buffer)
            if available >= frames:
                outdata[:, 0] = self._playback_buffer[:frames]
                self._playback_buffer = self._playback_buffer[frames:]
            elif available > 0:
                # Còn data nhưng không đủ frames: xả nốt, phần còn lại im lặng
                outdata[:available, 0] = self._playback_buffer
                outdata[available:, 0] = 0
                self._playback_buffer = np.zeros(0, dtype=np.float32)
            else:
                outdata.fill(0)

    # ─────────────────────────────────────────────
    # Playback Decoder Worker
    # ─────────────────────────────────────────────

    def _playback_worker(self):
        """
        Worker giải mã Base64 WAV → float32 PCM và append vào playback buffer.
        Chạy trong thread riêng để không block main thread.
        """
        while self._running:
            try:
                audio_b64 = self._playback_q.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                wav_bytes = base64.b64decode(audio_b64)
                with wave.open(io.BytesIO(wav_bytes)) as wf:
                    pcm       = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                    audio_f32 = pcm.astype(np.float32) / 32768.0

                with self._playback_lock:
                    self._playback_buffer = np.concatenate(
                        (self._playback_buffer, audio_f32)
                    )
            except Exception as e:
                logger.error(f"[AUDIO] Playback decode error: {e}")

    # ─────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────

    @staticmethod
    def list_devices():
        """In danh sách thiết bị audio Inbound (có âm thanh)."""
        print("\n--- Danh Sách Thiết Bị Inbound ---")
        for i, dev in enumerate(sd.query_devices()):
            if dev.get('max_input_channels', 0) > 0:
                print(f"🔊 {i} - {dev['name']} ({dev['max_input_channels']} in)")
        print("----------------------------------\n")