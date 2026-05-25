"""
scripts/test_drone_client.py
Script test giả lập Raspberry Pi 5 kết nối với Drone Edge Server.

Cách dùng:
  # Test bằng file audio WAV:
  python scripts/test_drone_client.py --audio path/to/command.wav

  # Test bằng mic thật (cần sounddevice):
  python scripts/test_drone_client.py --mic

  # Test nhanh bằng text mẫu (không cần mic):
  python scripts/test_drone_client.py --text "fly forward 2 meters"

  # Lệnh tiếng Việt (qua NLLB translation):
  python scripts/test_drone_client.py --text "bay tới trước 3 mét" --lang vi

Cài dependencies:
  pip install websockets numpy sounddevice scipy
"""
import argparse
import asyncio
import json
import sys
import time
import wave

import numpy as np
import websockets

# ─────────────────────────────────────────────────────────────────────────────
# Config — đổi IP nếu Edge Server không phải localhost
# ─────────────────────────────────────────────────────────────────────────────
SERVER_HOST = "localhost"
SERVER_PORT = 8765
API_KEY     = "drone-secret"
DRONE_ID    = "rpi5-test-01"
CHUNK_MS    = 500   # Gửi audio theo từng chunk 500ms
SAMPLE_RATE = 16000


def _print_result(msg: dict):
    """In kết quả nhận từ Server theo từng loại."""
    t = msg.get("type", "?")
    if t == "partial":
        print(f"  🎙️  STT (partial): {msg.get('text', '')}", end="\r")
    elif t == "command":
        latency = msg.get("latency_ms", 0)
        intent = msg.get("intent", "?")
        entities = msg.get("entities", {})
        conf = msg.get("confidence", 0)
        raw = msg.get("raw_text", "")
        en = msg.get("en_text", "")
        print(f"\n  ✅ COMMAND RECOGNIZED ({latency:.0f}ms):")
        print(f"     Raw text  : {raw}")
        if en and en != raw:
            print(f"     EN text   : {en}")
        print(f"     Intent    : {intent}")
        print(f"     Entities  : {entities}")
        print(f"     Confidence: {conf:.0%}")
        print(f"  → MAVLink sẽ nhận: {json.dumps({'cmd': intent, **entities}, ensure_ascii=False)}")
    elif t == "unknown":
        raw = msg.get("raw_text", "")
        latency = msg.get("latency_ms", 0)
        print(f"\n  ❓ UNKNOWN ({latency:.0f}ms): '{raw}' — Không nhận diện được intent")
    elif t == "error":
        print(f"\n  ❌ ERROR: {msg.get('message', '?')}")
    elif t == "reset_ok":
        print("\n  🔄 Buffer reset OK")


async def test_with_text(text: str, lang: str):
    """
    Test mode: Gửi text mẫu không qua audio.
    Dùng tính năng mock của Whisper (MOCK_TRANSCRIPTION_TEXT).
    Cần khởi động server với env: MOCK_TRANSCRIPTION_TEXT=<text>
    """
    uri = f"ws://{SERVER_HOST}:{SERVER_PORT}/drone/stream?api_key={API_KEY}&drone_id={DRONE_ID}&lang={lang}"
    print(f"\n🚁 Kết nối tới: {uri}")
    print(f"📝 Gửi text test: '{text}' (lang={lang})\n")

    # Tạo audio giả (1 giây silence) — Whisper sẽ được bypass bởi MOCK_TRANSCRIPTION_TEXT
    # hoặc chúng ta gửi thẳng qua endpoint REST để test nhanh
    print("  💡 Tip: Để test text mode, dùng lệnh curl sau:")
    print(f"  curl -X POST http://{SERVER_HOST}:8005/drone/classify -H 'Content-Type: application/json' -d '{{\"text\": \"{text}\"}}'")
    print()

    # Tạo 1s silence audio để mở kết nối, rồi trigger endpoint
    silence = np.zeros(SAMPLE_RATE, dtype=np.int16)
    audio_bytes = silence.tobytes()

    try:
        async with websockets.connect(uri) as ws:
            print("  ✅ WebSocket connected!")
            # Gửi 1 chunk silence
            await ws.send(audio_bytes)
            # Báo endpoint để trigger kết quả
            await ws.send(json.dumps({"event": "endpoint"}))

            # Nhận kết quả
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg = json.loads(response)
                _print_result(msg)
            except asyncio.TimeoutError:
                print("  ⚠️ Timeout: Server không trả về kết quả trong 10s")
    except Exception as e:
        print(f"  ❌ Lỗi kết nối: {e}")
        print("  → Đảm bảo server đang chạy: docker-compose -f docker-compose.drone.yml up -d")


async def test_with_wav(wav_path: str, lang: str):
    """Test mode: Đọc file WAV và stream lên Server."""
    uri = f"ws://{SERVER_HOST}:{SERVER_PORT}/drone/stream?api_key={API_KEY}&drone_id={DRONE_ID}&lang={lang}"
    print(f"\n🚁 Kết nối tới: {uri}")
    print(f"📁 File audio: {wav_path}\n")

    # Đọc WAV
    with wave.open(wav_path, "rb") as wf:
        channels    = wf.getnchannels()
        sample_rate = wf.getframerate()
        raw_audio   = wf.readframes(wf.getnframes())

    audio_np = np.frombuffer(raw_audio, dtype=np.int16)

    # Convert stereo → mono
    if channels == 2:
        audio_np = audio_np.reshape(-1, 2).mean(axis=1).astype(np.int16)

    # Resample nếu cần (đơn giản — dùng scipy nếu cần chính xác hơn)
    if sample_rate != SAMPLE_RATE:
        from scipy.signal import resample
        num_samples = int(len(audio_np) * SAMPLE_RATE / sample_rate)
        audio_np = resample(audio_np, num_samples).astype(np.int16)

    chunk_size = int(SAMPLE_RATE * CHUNK_MS / 1000)  # Số samples mỗi chunk

    try:
        async with websockets.connect(uri) as ws:
            print(f"  ✅ WebSocket connected! Đang stream {len(audio_np)/SAMPLE_RATE:.1f}s audio...\n")

            # Stream từng chunk
            for i in range(0, len(audio_np), chunk_size):
                chunk = audio_np[i:i + chunk_size].tobytes()
                await ws.send(chunk)
                await asyncio.sleep(CHUNK_MS / 1000)  # Giả lập realtime

                # Check partial result
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=0.01)
                    _print_result(json.loads(msg))
                except asyncio.TimeoutError:
                    pass

            # Báo kết thúc câu
            print("\n  📨 Gửi endpoint signal...")
            await ws.send(json.dumps({"event": "endpoint"}))

            # Nhận kết quả cuối
            try:
                while True:
                    response = await asyncio.wait_for(ws.recv(), timeout=15.0)
                    msg = json.loads(response)
                    _print_result(msg)
                    if msg.get("type") in ("command", "unknown", "error"):
                        break
            except asyncio.TimeoutError:
                print("  ⚠️ Timeout: Server không trả về kết quả trong 15s")

    except Exception as e:
        print(f"  ❌ Lỗi: {e}")


async def test_with_mic(lang: str):
    """Test mode: Ghi âm từ mic thật và stream lên Server."""
    try:
        import sounddevice as sd
    except ImportError:
        print("❌ Cần cài: pip install sounddevice")
        sys.exit(1)

    uri = f"ws://{SERVER_HOST}:{SERVER_PORT}/drone/stream?api_key={API_KEY}&drone_id={DRONE_ID}&lang={lang}"
    print(f"\n🚁 Kết nối tới: {uri}")
    print("🎤 Đang dùng mic — Nói lệnh điều khiển Drone, nhấn Ctrl+C để dừng\n")

    audio_queue: asyncio.Queue = asyncio.Queue()

    def callback(indata, frames, time_info, status):
        if status:
            print(f"  ⚠️ Mic warning: {status}", file=sys.stderr)
        audio_queue.put_nowait(bytes(indata))

    block_size = int(SAMPLE_RATE * CHUNK_MS / 1000)

    try:
        async with websockets.connect(uri) as ws:
            print("  ✅ WebSocket connected! Đang nghe mic...\n")

            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=block_size,
                callback=callback,
            ):
                is_listening = True
                try:
                    while is_listening:
                        # Gửi chunk audio
                        chunk = await audio_queue.get()
                        await ws.send(chunk)

                        # Check partial results không blocking
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=0.01)
                            _print_result(json.loads(msg))
                        except asyncio.TimeoutError:
                            pass

                except KeyboardInterrupt:
                    print("\n\n  ⏹️  Kết thúc ghi âm, gửi endpoint...")
                    await ws.send(json.dumps({"event": "endpoint"}))

                    # Nhận kết quả cuối
                    try:
                        while True:
                            response = await asyncio.wait_for(ws.recv(), timeout=15.0)
                            msg = json.loads(response)
                            _print_result(msg)
                            if msg.get("type") in ("command", "unknown", "error"):
                                break
                    except asyncio.TimeoutError:
                        print("  ⚠️ Timeout: Server không trả về kết quả trong 15s")

    except Exception as e:
        print(f"  ❌ Lỗi kết nối: {e}")
        print("  → Đảm bảo server đang chạy: docker-compose -f docker-compose.drone.yml up -d")


async def test_classify_rest(text: str, lang: str):
    """Test nhanh endpoint REST /drone/classify (không cần audio)."""
    import httpx
    url = f"http://{SERVER_HOST}:8005/drone/classify"
    print(f"\n🚁 Test REST endpoint: POST {url}")
    print(f"📝 Text: '{text}' (lang={lang})\n")

    # Nếu lệnh tiếng Việt → dịch sang tiếng Anh trước
    en_text = text
    if lang == "vi":
        print("  🌐 Đang dịch Việt → Anh qua NLLB...")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"http://{SERVER_HOST}:8002/translate",
                    json={"text": text, "src_lang": "vie_Latn", "tgt_lang": "eng_Latn"}
                )
                en_text = resp.json().get("translated_text", text)
                print(f"  ✅ Dịch xong: '{en_text}'\n")
        except Exception as e:
            print(f"  ⚠️ NLLB không khả dụng: {e}")

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json={"text": en_text})
            data = resp.json()
            latency = (time.perf_counter() - t0) * 1000

        print(f"  ✅ Kết quả ({latency:.0f}ms):")
        print(f"     Intent    : {data.get('intent', 'None')}")
        print(f"     Entities  : {data.get('entities', {})}")
        print(f"     Confidence: {data.get('confidence', 0):.0%}")
        print(f"     Latency   : {data.get('latency_ms', 0):.0f}ms (LLM)")
    except Exception as e:
        print(f"  ❌ Lỗi: {e}")
        print("  → Đảm bảo agent-service đang chạy trên port 8005")


def main():
    parser = argparse.ArgumentParser(
        description="🚁 Drone Edge Server Test Client (giả lập Raspberry Pi 5)"
    )
    parser.add_argument("--host",  default="localhost", help="IP của Edge Server (mặc định: localhost)")
    parser.add_argument("--port",  default=8765, type=int, help="WebSocket port (mặc định: 8765)")
    parser.add_argument("--lang",  default="en", choices=["en", "vi"], help="Ngôn ngữ lệnh")
    parser.add_argument("--key",   default="drone-secret", help="API key")
    parser.add_argument("--text",  help="Test nhanh với text mẫu qua REST endpoint")
    parser.add_argument("--audio", help="Test với file WAV")
    parser.add_argument("--mic",   action="store_true", help="Test với mic thật")
    args = parser.parse_args()

    global SERVER_HOST, SERVER_PORT, API_KEY
    SERVER_HOST = args.host
    SERVER_PORT = args.port
    API_KEY     = args.key

    print("=" * 60)
    print("  🚁 Drone Edge Server — Test Client")
    print(f"  Server : ws://{SERVER_HOST}:{SERVER_PORT}")
    print(f"  Lang   : {args.lang}")
    print("=" * 60)

    if args.text:
        asyncio.run(test_classify_rest(args.text, args.lang))
    elif args.audio:
        asyncio.run(test_with_wav(args.audio, args.lang))
    elif args.mic:
        asyncio.run(test_with_mic(args.lang))
    else:
        print("\n📖 Ví dụ sử dụng:")
        print("  # Test lệnh tiếng Anh (nhanh, qua REST):")
        print("  python scripts/test_drone_client.py --text 'fly forward 2 meters'")
        print()
        print("  # Test lệnh tiếng Việt:")
        print("  python scripts/test_drone_client.py --text 'bay tới trước 3 mét' --lang vi")
        print()
        print("  # Test bằng file WAV:")
        print("  python scripts/test_drone_client.py --audio command.wav --lang en")
        print()
        print("  # Test bằng mic:")
        print("  python scripts/test_drone_client.py --mic --lang vi")
        print()
        print("  # Kết nối đến server khác (ví dụ RTX A4000):")
        print("  python scripts/test_drone_client.py --host 192.168.1.100 --text 'take off'")
        print()
        parser.print_help()


if __name__ == "__main__":
    main()
