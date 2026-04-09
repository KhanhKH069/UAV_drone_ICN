"""
client/audio_router/inbound_audio_manager.py
FIX: Use PyTorch Silero VAD instead of ONNX (ONNX version not working)
"""

import base64
import datetime
import logging
import os
import queue
import threading
import time
import wave
from collections import deque
from math import gcd
from typing import Callable, Optional
from dotenv import load_dotenv

load_dotenv(override=True)

import numpy as np
import sounddevice as sd

logger = logging.getLogger("paraline.audio.inbound")

SAMPLE_RATE    = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
CHUNK_MS       = int(os.getenv("AUDIO_CHUNK_MS", "96"))
CHUNK_SAMP     = SAMPLE_RATE * CHUNK_MS // 1000
VIRTUAL_SPK    = os.getenv("VIRTUAL_SPEAKER_NAME", "pulse")

VAD_THRESHOLD  = float(os.getenv("VAD_SPEECH_THRESHOLD", "0.6"))  # PyTorch uses higher threshold
SILENCE_CHUNKS = int(os.getenv("SILENCE_CHUNKS_LIMIT", "3"))  # 2 chunks x 96ms = ~200ms silence to end sentence
MAX_CHUNKS     = int(os.getenv("MAX_SENTENCE_CHUNKS", "100"))  # ~7.5s max sentence length to prevent infinite buffering
HISTORY_CHUNKS = int(os.getenv("HISTORY_CHUNKS", "2"))

SPEC_OVER_SUB  = float(os.getenv("SPEC_OVER_SUBTRACTION_IN", "0.8"))
SPEC_FLOOR     = float(os.getenv("SPEC_FLOOR_RATIO_IN", "0.05"))
NOISE_ALPHA    = float(os.getenv("NOISE_ALPHA_IN", "0.1"))

NORM_TARGET    = float(os.getenv("NORMALIZE_TARGET_RMS", "0.1"))
NORM_MAX_GAIN  = float(os.getenv("NORMALIZE_MAX_GAIN_IN", "3.0"))

WHISPER_PAD_MS = int(os.getenv("WHISPER_PAD_MS", "300"))
MIN_AUDIO_SEC  = float(os.getenv("MIN_AUDIO_SEC", "0.3"))

DEBUG_AUDIO    = os.getenv("DEBUG_AUDIO", "0") == "1"
DEBUG_DIR      = os.getenv("DEBUG_AUDIO_DIR", "debug_audio/inbound")
DEBUG_RMS_SEC  = float(os.getenv("DEBUG_RMS_INTERVAL", "3.0"))

# PyTorch VAD settings
VAD_WINDOW_MS = int(os.getenv("VAD_WINDOW_MS", "30"))  # 30ms window
VAD_WINDOW_SAMPS = int(SAMPLE_RATE * VAD_WINDOW_MS / 1000)


class InboundAudioManager:
    def __init__(self):
        self._running = False
        self._callback: Optional[Callable[[str], None]] = None

        self._in_q = queue.Queue(maxsize=200)
        self._noise_lock = threading.Lock()
        self._noise_profile: Optional[np.ndarray] = None
        self._last_dbg = 0.0

        # PyTorch VAD
        self._vad_model = None
        self._vad_utils = None
        self._get_speech_timestamps = None
        self._audio_buffer = np.array([], dtype=np.float32)

        self._stream: Optional[sd.InputStream] = None
        self._device_rate: int = SAMPLE_RATE
        self._resample_buf: np.ndarray = np.array([], dtype=np.float32)

    # ── Public API ───────────────────────────────────────────

    def start(self, callback: Callable[[str], None], device_name: Optional[str] = None):
        self._callback = callback
        self._running = True

        dev_name = device_name or VIRTUAL_SPK
        
        # Xử lý định dạng "pulse::<source_name>" hoặc "alsa::<device_name>" từ UI
        if dev_name and "::" in dev_name:
            dev_type, real_name = dev_name.split("::", 1)
            if dev_type == "pulse":
                os.environ["PULSE_SOURCE"] = real_name
                print(f"[INBOUND] Set environment variable PULSE_SOURCE = {real_name}")
                # Sounddevice không tự thấy được .monitor, phải nhờ backend PulseAudio route qua biến PULSE_SOURCE
                dev = self._find_device("pulse", input=True) or self._find_device("default", input=True)
                print(f"\n[INBOUND] Dùng '{dev}' device để đọc từ PulseAudio Source [{real_name}]")
            else:
                dev = self._find_device(real_name, input=True)
                print(f"\n[INBOUND] Thiết bị ALSA : {real_name} [idx: {dev}]")
        else:
            dev = self._find_device(dev_name, input=True)
            print(f"\n[INBOUND] Thiết bị mặc định : {dev_name} [idx: {dev}]")

        if dev is not None:
            dev_info = sd.query_devices(dev)
            self._device_rate = int(dev_info["default_samplerate"])
            print(f"[INBOUND] Native device rate  : {self._device_rate}Hz")
            print(f"[INBOUND] Pipeline target rate : {SAMPLE_RATE}Hz")
            if self._device_rate != SAMPLE_RATE:
                print(f"[INBOUND] Resample ratio: {self._device_rate}->{SAMPLE_RATE}Hz (scipy polyphase)")
        else:
            self._device_rate = SAMPLE_RATE

        print(f"[INBOUND] Chunk: {CHUNK_MS}ms ({CHUNK_SAMP} samples @ {SAMPLE_RATE}Hz)")
        print(f"[INBOUND] VAD threshold: {VAD_THRESHOLD} | silence={SILENCE_CHUNKS}x{CHUNK_MS}ms")

        # Load PyTorch VAD
        if not self._load_vad_model():
            print("[INBOUND] WARNING: PyTorch VAD not available, using simple RMS VAD")

        if dev is not None:
            native_chunk = self._device_rate * CHUNK_MS // 1000
            self._stream = sd.InputStream(
                device=dev,
                samplerate=self._device_rate,
                channels=1,
                dtype="int16",
                blocksize=native_chunk,
                callback=self._hw_cb,
            )
            self._stream.start()
            logger.info(f"[INBOUND] Stream started [{dev}] @ {self._device_rate}Hz")
        else:
            logger.warning("[INBOUND] Khong tim thay Virtual Cable -- mock mode")
            threading.Thread(target=self._mock, daemon=True).start()

        threading.Thread(target=self._vad_worker, name="InboundVAD", daemon=True).start()

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.info("[INBOUND] Stopped")

    # ── PyTorch VAD Load ────────────────────────────────────

    def _load_vad_model(self) -> bool:
        """Load Silero VAD using PyTorch (works correctly)"""
        try:
            import torch
            
            # Force CPU mode
            torch.set_num_threads(1)
            device = torch.device('cpu')
            
            print("[INBOUND] Loading PyTorch Silero VAD...")
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False,
                verbose=False
            )
            
            model = model.to(device)
            model.eval()
            
            self._vad_model = model
            self._vad_utils = utils
            self._get_speech_timestamps = utils[0]  # get_speech_timestamps
            
            print(f"[INBOUND] PyTorch Silero VAD loaded | threshold={VAD_THRESHOLD}")
            return True
            
        except Exception as e:
            print(f"[INBOUND] Failed to load PyTorch VAD: {e}")
            return False

    def _check_speech_pytorch(self, audio_chunk: np.ndarray) -> bool:
        """
        Check if current audio chunk contains speech using PyTorch VAD Streaming API.
        Trả về True nếu CÓ TIẾNG NGƯỜI (Speech).
        """
        if self._vad_model is None:
            return self._rms_vad(audio_chunk)
        
        try:
            import torch
            
            # Silero VAD hoạt động chuẩn nhất với cửa sổ 512 samples (32ms)
            # Chunk đầu vào của bạn là 96ms (1536 samples), nên ta chia làm 3 phần
            window_size = 512
            max_prob = 0.0
            
            # Tắt tính toán gradient để tăng tốc CPU
            with torch.no_grad():
                for start in range(0, len(audio_chunk), window_size):
                    window = audio_chunk[start:start+window_size]
                    
                    # Pad nếu chunk bị lẻ
                    if len(window) < window_size:
                        window = np.pad(window, (0, window_size - len(window)))
                        
                    # Chuyển thành tensor (batch_size=1, sequence_length=512)
                    tensor = torch.from_numpy(window).float().unsqueeze(0)
                    
                    # Gọi thẳng model để lấy xác suất. Model sẽ tự động lưu memory (state)
                    prob = self._vad_model(tensor, SAMPLE_RATE).item()
                    max_prob = max(max_prob, prob)
            
            # # Debug thanh trạng thái (tùy chọn)
            # bar_len = int(max_prob * 10)
            # print(f"[VAD] {max_prob:.2f} [{'#'*bar_len}{'-'*(10-bar_len)}]")

            # Nếu max_prob vượt ngưỡng, xác nhận có tiếng người
            if max_prob >= VAD_THRESHOLD:
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"[VAD ERROR] {e}")
            return self._rms_vad(audio_chunk)

    # ── Hardware callback ────────────────────────────────────

    def _hw_cb(self, indata, frames, time_info, status):
        if not self._running:
            return

        if status:
            logger.warning(f"[INBOUND HW] sounddevice status: {status}")

        if self._device_rate != SAMPLE_RATE:
            chunk_target = self._resample_to_target(indata.flatten())
        else:
            chunk_target = indata.flatten().astype(np.float32)

        self._resample_buf = np.concatenate([self._resample_buf, chunk_target])

        while len(self._resample_buf) >= CHUNK_SAMP:
            out_chunk = self._resample_buf[:CHUNK_SAMP].astype(np.int16)
            self._resample_buf = self._resample_buf[CHUNK_SAMP:]
            try:
                self._in_q.put_nowait(out_chunk.reshape(-1, 1))
            except queue.Full:
                try:
                    self._in_q.get_nowait()
                    self._in_q.put_nowait(out_chunk.reshape(-1, 1))
                except queue.Empty:
                    pass

    def _resample_to_target(self, audio_int16: np.ndarray) -> np.ndarray:
        try:
            from scipy.signal import resample_poly
            g = gcd(SAMPLE_RATE, self._device_rate)
            up = SAMPLE_RATE // g
            down = self._device_rate // g
            resampled = resample_poly(audio_int16.astype(np.float32), up, down)
            return resampled
        except ImportError:
            n_out = int(len(audio_int16) * SAMPLE_RATE / self._device_rate)
            x_old = np.linspace(0, 1, len(audio_int16))
            x_new = np.linspace(0, 1, n_out)
            return np.interp(x_new, x_old, audio_int16.astype(np.float32))

    # ── VAD Worker ───────────────────────────────────────────

    def _vad_worker(self):
        buf = []
        history = deque(maxlen=HISTORY_CHUNKS)
        speaking = False
        sil_count = 0

        while self._running:
            try:
                chunk = self._in_q.get(timeout=0.1)
            except queue.Empty:
                continue

            now = time.time()
            if now - self._last_dbg >= DEBUG_RMS_SEC:
                rms = np.sqrt(np.mean((chunk.astype(np.float32) / 32768.0) ** 2))
                print(f"[INBOUND RMS] {rms:.5f}")
                self._last_dbg = now

            # Convert to float32 for VAD
            chunk_float = chunk.flatten().astype(np.float32) / 32768.0
            is_silence = not self._check_speech_pytorch(chunk_float)

            if is_silence:
                self._update_noise(chunk)

            if not is_silence:
                if not speaking:
                    speaking = True
                    sil_count = 0
                    buf.extend(list(history))
                    history.clear()
                    print("[INBOUND VAD] >>> Bat dau cau...")
                buf.append(chunk)
                sil_count = 0
            else:
                if speaking:
                    buf.append(chunk)
                    sil_count += 1
                    print(f"[INBOUND VAD] silence {sil_count}/{SILENCE_CHUNKS}...")
                    if sil_count >= SILENCE_CHUNKS:
                        duration_s = len(buf) * CHUNK_MS / 1000.0
                        print(f"[INBOUND VAD] Ngat cau -> Gui {duration_s:.2f}s")
                        self._send(buf)
                        buf, speaking, sil_count = [], False, 0
                        history.clear()
                else:
                    history.append(chunk)

            if speaking and len(buf) >= MAX_CHUNKS:
                duration_ms = len(buf) * CHUNK_MS
                print(f"[INBOUND VAD] Cat ngang ({duration_ms}ms), MAX_CHUNKS={MAX_CHUNKS}")
                self._send(buf)
                buf, speaking, sil_count = [], False, 0
                history.clear()

    def _rms_vad(self, chunk: np.ndarray, thr: float = 0.015) -> bool:
        """Fallback VAD based on RMS energy (less accurate)"""
        rms = np.sqrt(np.mean((chunk.astype(np.float32) / 32768.0) ** 2))
        return rms > thr

    # ── Processing Pipeline ──────────────────────────────────

    def _send(self, buf: list):
        if not buf:
            return

        duration_s = len(buf) * CHUNK_MS / 1000.0
        print(f"[INBOUND] _send({len(buf)} chunks, ~{duration_s:.2f}s raw)")

        audio = np.concatenate(buf).flatten()

        # tắt lọc nhiễu tạm thời vì có thể làm méo tiếng, đồng thời PyTorch VAD đã khá ổn rồi
        # audio = self._spec_sub(audio)

        f32 = audio.astype(np.float32) / 32768.0

        # cắt bỏ phần đầu cuối im lặng thừa (nếu có), tránh gửi lên Whisper toàn bộ 7-8s audio có nhiều khoảng lặng
        # f32 = self._trim(f32, thr=0.02)

        if len(f32) < int(SAMPLE_RATE * MIN_AUDIO_SEC):
            print(f"[INBOUND] Bo qua: {len(f32)/SAMPLE_RATE*1000:.0f}ms qua ngan")
            return

        # f32 = self._normalize_sentence(f32)
        f32 = np.clip(f32, -1.0, 1.0)

        pad = np.zeros(int(SAMPLE_RATE * WHISPER_PAD_MS / 1000), dtype=np.float32)
        f32 = np.concatenate([pad, f32, pad])

        if DEBUG_AUDIO:
            p = self._save_wav(f32)
            if p:
                print(f"[DEBUG] Saved: {p}")

        print(f"[INBOUND] >>> Gui {len(f32)/SAMPLE_RATE:.2f}s len server")
        b64 = base64.b64encode(f32.tobytes()).decode()
        if self._callback:
            try:
                self._callback(b64)
            except Exception as e:
                logger.error(f"[INBOUND] Callback error: {e}")

    # ── Spectral Subtraction ─────────────────────────────────

    def _update_noise(self, chunk: np.ndarray):
        flat = chunk.flatten().astype(np.float32)
        spec = np.abs(np.fft.rfft(flat))
        with self._noise_lock:
            if self._noise_profile is None:
                self._noise_profile = spec.copy()
            elif len(spec) == len(self._noise_profile):
                self._noise_profile = (
                    (1 - NOISE_ALPHA) * self._noise_profile + NOISE_ALPHA * spec
                )

    def _spec_sub(self, audio: np.ndarray) -> np.ndarray:
        with self._noise_lock:
            noise = self._noise_profile
        if noise is None:
            return audio

        flat = audio.flatten().astype(np.float32)
        n = len(flat)
        spec = np.fft.rfft(flat)
        mag = np.abs(spec)
        phase = np.angle(spec)
        L = min(len(mag), len(noise))

        clean_mag = np.maximum(
            mag[:L] - SPEC_OVER_SUB * noise[:L],
            SPEC_FLOOR * mag[:L],
        )
        clean = np.zeros(len(spec), dtype=complex)
        clean[:L] = clean_mag * np.exp(1j * phase[:L])
        if L < len(spec):
            clean[L:] = spec[L:]

        return np.clip(np.fft.irfft(clean, n=n), -32768, 32767).astype(np.int16)

    # ── Trim / Normalize ─────────────────────────────────────

    def _trim(self, audio: np.ndarray, thr: float = 0.005, pad: int = 800) -> np.ndarray:
        idx = np.where(np.abs(audio) > thr)[0]
        if len(idx) == 0:
            return audio
        return audio[max(0, idx[0] - pad) : min(len(audio), idx[-1] + pad)]

    def _normalize_sentence(self, audio: np.ndarray) -> np.ndarray:
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 1e-6:
            return audio
        gain = np.clip(NORM_TARGET / rms, 0.1, NORM_MAX_GAIN)
        print(f"[INBOUND] normalize gain={gain:.2f} (rms={rms:.5f})")
        return audio * gain

    # ── Debug / Utils ────────────────────────────────────────

    def _save_wav(self, f32: np.ndarray) -> Optional[str]:
        try:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            ts = datetime.datetime.now().strftime("%H%M%S_%f")
            dur = len(f32) / SAMPLE_RATE
            p = os.path.join(DEBUG_DIR, f"in_{dur:.1f}s_{ts}.wav")
            with wave.open(p, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes((f32 * 32767).astype(np.int16).tobytes())
            return p
        except Exception as e:
            logger.error(f"[INBOUND] Save WAV error: {e}")
            return None

    def _mock(self):
        time.sleep(1)
        t_idx = 0
        for _ in range(3):
            if not self._running:
                break
            for _ in range(6):
                t = np.linspace(t_idx / SAMPLE_RATE,
                                (t_idx + CHUNK_SAMP) / SAMPLE_RATE,
                                CHUNK_SAMP, endpoint=False)
                sig = (0.3 * 32767 * np.sin(2 * np.pi * 440 * t)).astype(np.int16)
                t_idx += CHUNK_SAMP
                try:
                    self._in_q.put_nowait(sig.reshape(-1, 1))
                except queue.Full:
                    pass
                time.sleep(CHUNK_MS / 1000)
            sil = np.zeros((CHUNK_SAMP, 1), dtype=np.int16)
            for _ in range(SILENCE_CHUNKS + 1):
                try:
                    self._in_q.put_nowait(sil)
                except queue.Full:
                    pass
                time.sleep(CHUNK_MS / 1000)
            time.sleep(1.0)

    @staticmethod
    def _find_device(name: str, input: bool = True) -> Optional[int]:
        devices = sd.query_devices()
        
        # Ưu tiên tìm tên khớp hoàn toàn (Case-insensitive)
        for i, d in enumerate(devices):
            if name.lower() in d["name"].lower():
                print(f"[INBOUND] Đã tìm thấy thiết bị khớp: {d['name']} (ID: {i})")
                return i
                
        print(f"❌ CẢNH BÁO: Không tìm thấy thiết bị nào tên '{name}'!")
        return None # Khi trả về None, bạn phải xử lý ở hàm start để không dùng Mic mặc định