# """
# client/websocket_client/ws_client.py
# WebSocket Stream Controller.
# Vexa pattern: client connects to WhisperLive WebSocket stream.

# Duy trì 2 WebSocket connections song song:
#   /ws/audio/{session_id}?direction=inbound   ← Virtual Speaker (Teams audio)
#   /ws/audio/{session_id}?direction=outbound  ← Real Microphone
# """
# import asyncio
# import json
# import logging
# import threading
# from typing import Callable, Optional

# import websockets
# from websockets.exceptions import ConnectionClosed

# logger = logging.getLogger("paraline.ws")


# class ParalineWSClient:
#     def __init__(
#         self,
#         server_ws_url: str,   # e.g. "ws://192.168.1.100:8765"
#         session_id: str,
#         api_key: str = "",
#         on_subtitle:      Optional[Callable[[str, float], None]] = None,
#         on_inbound_audio: Optional[Callable[[str], None]] = None,
#         on_outbound_text: Optional[Callable[[str, str], None]] = None,
#         on_error:         Optional[Callable[[str], None]] = None,
#     ):
#         self.base_url   = server_ws_url
#         self.session_id = session_id
#         self.api_key    = api_key

#         self._on_subtitle      = lambda src, dst, ms: self.sig_subtitle.emit(src, dst, ms), on_subtitle or (lambda *args: None)
#         self._on_inbound_audio = on_inbound_audio
#         self._on_outbound_text = on_outbound_text
#         self._on_error         = on_error

#         self._running = False
#         self._loop    = asyncio.new_event_loop()
#         self._thread  = threading.Thread(target=self._run, daemon=True)

#         # Thread-safe queues (put from audio callback threads)
#         self._inbound_q  = asyncio.Queue(maxsize=100)
#         self._outbound_q = asyncio.Queue(maxsize=100)

#         # Language config
#         self.inbound_src_lang  = "eng_Latn"
#         self.inbound_tgt_lang  = "vie_Latn"
#         self.outbound_src_lang = "vie_Latn"
#         self.outbound_tgt_lang = "eng_Latn"

#         # ─────────────────────────────────────────────
#         # CHỎ FLAG NÀY ĐỂ ĐIỀU KHIỂN LUỔNG
#         # True  = Chỉ nghe Inbound (người kia nói), bỏ qua Outbound (mic của bạn)
#         # False = Chạy cả 2 luồng song song
#         # ─────────────────────────────────────────────
#         self.inbound_only = True


#         self._last_inbound_final  = ""
#         self._last_outbound_final = ""

#         self._partial_inbound  = ""
#         self._partial_outbound = ""

#         # self._last_ui_outbound = None


#     # ─────────────────────────────────────────────
#     # Public API
#     # ─────────────────────────────────────────────

#     def start(self):
#         self._running = True
#         self._thread.start()
#         logger.info(f"WS client started — session {self.session_id[:8]}")

#     def stop(self):
#         self._running = False
#         # Do not force loop.stop(), let tasks finish naturally via timeout
#         if self._loop.is_running():
#             self._loop.call_soon_threadsafe(self._cancel_all_tasks)

#     def _cancel_all_tasks(self):
#         for task in asyncio.all_tasks(self._loop):
#             task.cancel()

#     def send_inbound_chunk(self, pcm_b64: str):
#         """Call from audio thread: push inbound audio chunk."""
#         self._loop.call_soon_threadsafe(
#             lambda: self._inbound_q.put_nowait(pcm_b64) if not self._inbound_q.full() else None
#         )

#     def send_outbound_chunk(self, pcm_b64: str):
#         """Call from audio thread: push outbound audio chunk."""
#         self._loop.call_soon_threadsafe(
#             lambda: self._outbound_q.put_nowait(pcm_b64) if not self._outbound_q.full() else None
#         )

#     # ─────────────────────────────────────────────
#     # Internal
#     # ─────────────────────────────────────────────

#     def _run(self):
#         asyncio.set_event_loop(self._loop)
#         try:
#             loops = [self._inbound_ws_loop()]
#             if not self.inbound_only:
#                 loops.append(self._outbound_ws_loop())
#                 logger.info("WS: Chạy cả 2 luồng Inbound + Outbound")
#             else:
#                 logger.info("WS: Chỉ chạy Inbound (inbound_only=True)")
#                 print("[🎧 WS] Chỉ  chạy Inbound — bỏ qua mic Outbound.", flush=True)
#             self._loop.run_until_complete(asyncio.gather(*loops))
#         except asyncio.CancelledError:
#             pass
#         except Exception as e:
#             logger.debug(f"WS loop exit: {e}")

#     def _ws_url(self, direction: str) -> str:
#         return (f"{self.base_url}/ws/audio/{self.session_id}"
#                 f"?direction={direction}&api_key={self.api_key}")

#     async def _inbound_ws_loop(self):
#         """Inbound: Virtual Speaker → server → TTS audio + subtitle."""
#         while self._running:
#             try:
#                 async with websockets.connect(self._ws_url("inbound"), ping_interval=20) as ws:
#                     logger.info("Inbound WS connected ✓")
#                     await asyncio.gather(
#                         self._sender(ws, self._inbound_q, self.inbound_src_lang, self.inbound_tgt_lang),
#                         self._receiver(ws, "inbound"),
#                     )
#             except ConnectionClosed:
#                 logger.warning("Inbound WS closed. Reconnecting...")
#             except Exception as e:
#                 logger.error(f"Inbound WS error: {e}")
#             if self._running:
#                 await asyncio.sleep(2)

#     async def _outbound_ws_loop(self):
#         """Outbound: Real Mic → server → Teams text."""
#         while self._running:
#             try:
#                 async with websockets.connect(self._ws_url("outbound"), ping_interval=20) as ws:
#                     logger.info("Outbound WS connected ✓")
#                     await asyncio.gather(
#                         self._sender(ws, self._outbound_q, self.outbound_src_lang, self.outbound_tgt_lang),
#                         self._receiver(ws, "outbound"),
#                     )
#             except ConnectionClosed:
#                 logger.warning("Outbound WS closed. Reconnecting...")
#             except Exception as e:
#                 logger.error(f"Outbound WS error: {e}")
#             if self._running:
#                 await asyncio.sleep(2)

#     async def _sender(self, ws, queue: asyncio.Queue, src: str, tgt: str):
#         """Continuously drain queue and send audio chunks."""
#         idx = 0
#         while self._running:
#             try:
#                 data = await asyncio.wait_for(queue.get(), timeout=0.5)
#                 await ws.send(json.dumps({
#                     "type":        "audio_chunk",
#                     "data":        data,
#                     "src_lang":    src,
#                     "tgt_lang":    tgt,
#                     "session_id":  self.session_id,
#                     "chunk_index": idx,
#                 }))
#                 idx += 1
#             except asyncio.TimeoutError:
#                 continue
#             except Exception as e:
#                 logger.debug(f"Sender error: {e}")
#                 break

#     async def _receiver(self, ws, direction: str):
#         async for msg in ws:
#             try:
#                 data = json.loads(msg)
#                 t = data.get("type", "")

#                 # =========================
#                 # ❌ BỎ subtitle (spam)
#                 # =========================
#                 if t == "subtitle":
#                     continue

#                 # =========================
#                 # ✅ INBOUND (FINAL ONLY)
#                 # =========================
#                 elif t == "inbound_result":
#                     orig = data.get("original_text", "").strip()
#                     translated = data.get("translated_text", "").strip()
#                     is_final = data.get("is_final", True)  # fallback nếu server chưa có field này

#                     if not translated:
#                         continue

#                     if not is_final:
#                         # update partial (không render UI)
#                         self._partial_inbound = translated
#                         continue

#                     # FINAL → chống duplicate
#                     if translated == self._last_inbound_final:
#                         continue

#                     self._last_inbound_final = translated

#                     print(f"📝 [FINAL INBOUND] {translated}")

#                     if self._on_subtitle:
#                         self._on_subtitle(orig , translated, data.get("latency_ms", 0))

#                     if self._on_inbound_audio and data.get("audio_b64"):
#                         self._on_inbound_audio(data["audio_b64"])

#                 # =========================
#                 # ✅ OUTBOUND (FINAL ONLY)
#                 # =========================
#                 elif t == "outbound_result":
#                     orig = data.get("original_text", "").strip()
#                     trans = data.get("translated_text", "").strip()
#                     is_final = data.get("is_final", True)

#                     if not trans:
#                         continue

#                     if not is_final:
#                         self._partial_outbound = trans
#                         continue

#                     if trans == self._last_outbound_final:
#                         continue

#                     self._last_outbound_final = trans

#                     print(f"📝 [FINAL OUTBOUND] {orig} → {trans}")

#                     if self._on_outbound_text:
#                         self._on_outbound_text(orig, trans)

#                 # =========================
#                 # ERROR
#                 # =========================
#                 elif t == "error":
#                     msg_err = data.get("message", "Unknown error")
#                     print(f"❌ [LỖI SERVER]: {msg_err}")
#                     if self._on_error:
#                         self._on_error(msg_err)

#             except Exception as e:
#                 logger.error(f"Receiver error [{direction}]: {e}")


import asyncio
import json
import logging
import threading
from typing import Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger("paraline.ws")


class ParalineWSClient:
    def __init__(
        self,
        server_ws_url: str,
        session_id: str,
        api_key: str = "",
        on_subtitle: Optional[Callable[[str, str, float], None]] = None,
        on_inbound_audio: Optional[Callable[[str], None]] = None,
        on_outbound_text: Optional[Callable[[str, str], None]] = None,
        on_listening: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.base_url = server_ws_url
        self.session_id = session_id
        self.api_key = api_key

        # ✅ FIX: gán đúng function
        self._on_subtitle = on_subtitle
        self._on_inbound_audio = on_inbound_audio
        self._on_outbound_text = on_outbound_text
        self._on_listening = on_listening
        self._on_error = on_error

        self._running = False
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)

        self._inbound_q = asyncio.Queue(maxsize=100)
        self._outbound_q = asyncio.Queue(maxsize=100)

        self.inbound_src_lang = "eng_Latn"
        self.inbound_tgt_lang = "vie_Latn"
        self.outbound_src_lang = "vie_Latn"
        self.outbound_tgt_lang = "eng_Latn"

        self.inbound_only = True

        # chống duplicate
        self._last_inbound_final = ""
        self._last_outbound_final = ""

    # ─────────────────────────────────────────────

    def start(self):
        self._running = True
        self._thread.start()
        logger.info(f"WS client started — session {self.session_id[:8]}")

    def stop(self):
        self._running = False
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._cancel_all_tasks)

    def _cancel_all_tasks(self):
        for task in asyncio.all_tasks(self._loop):
            task.cancel()

    def send_inbound_chunk(self, pcm_b64: str, is_final: bool = True):
        self._loop.call_soon_threadsafe(
            lambda: self._inbound_q.put_nowait((pcm_b64, is_final)) if not self._inbound_q.full() else None
        )

    def send_outbound_chunk(self, pcm_b64: str):
        self._loop.call_soon_threadsafe(
            lambda: self._outbound_q.put_nowait(pcm_b64) if not self._outbound_q.full() else None
        )

    # ─────────────────────────────────────────────

    def _run(self):
        asyncio.set_event_loop(self._loop)
        try:
            loops = [self._inbound_ws_loop()]
            if not self.inbound_only:
                loops.append(self._outbound_ws_loop())
            self._loop.run_until_complete(asyncio.gather(*loops))
        except Exception as e:
            logger.debug(f"WS loop exit: {e}")

    def _ws_url(self, direction: str) -> str:
        return f"{self.base_url}/ws/audio/{self.session_id}?direction={direction}&api_key={self.api_key}"

    async def _inbound_ws_loop(self):
        while self._running:
            try:
                async with websockets.connect(self._ws_url("inbound")) as ws:
                    await asyncio.gather(
                        self._sender(ws, self._inbound_q, "inbound"),
                        self._receiver(ws, "inbound"),
                    )
            except Exception:
                await asyncio.sleep(2)

    async def _outbound_ws_loop(self):
        while self._running:
            try:
                async with websockets.connect(self._ws_url("outbound")) as ws:
                    await asyncio.gather(
                        self._sender(ws, self._outbound_q, "outbound"),
                        self._receiver(ws, "outbound"),
                    )
            except Exception:
                await asyncio.sleep(2)

    async def _sender(self, ws, queue: asyncio.Queue, direction: str):
        idx = 0
        while self._running:
            try:
                msg_data = await asyncio.wait_for(queue.get(), timeout=0.5)
                if isinstance(msg_data, tuple):
                    data, is_final = msg_data
                else:
                    data, is_final = msg_data, True
                
                # Fetch language dynamically
                if direction == "inbound":
                    src = self.inbound_src_lang
                    tgt = self.inbound_tgt_lang
                else:
                    src = self.outbound_src_lang
                    tgt = self.outbound_tgt_lang

                await ws.send(json.dumps({
                    "type": "audio_chunk",
                    "data": data,
                    "src_lang": src,
                    "tgt_lang": tgt,
                    "is_final": is_final,
                    "session_id": self.session_id,
                    "chunk_index": idx,
                }))
                idx += 1
            except asyncio.TimeoutError:
                continue

    async def _receiver(self, ws, direction: str):
        async for msg in ws:
            try:
                data = json.loads(msg)
                t = data.get("type", "")

                if t == "subtitle":
                    continue

                elif t == "listening":
                    text = data.get("text", "")
                    if self._on_listening:
                        self._on_listening(text)
                    continue

                # =========================
                # INBOUND
                # =========================
                elif t == "inbound_result":
                    orig = data.get("original_text", "").strip()
                    trans = data.get("translated_text", "").strip()
                    is_final = data.get("is_final", True)

                    if not trans or not is_final:
                        continue

                    key = f"{orig}|{trans}"
                    if key == self._last_inbound_final:
                        continue
                    self._last_inbound_final = key

                    print(f"📝 [INBOUND] {orig} → {trans}")

                    if self._on_subtitle:
                        self._on_subtitle(orig, trans, data.get("latency_ms", 0))

                    if self._on_inbound_audio and data.get("audio_b64"):
                        self._on_inbound_audio(data["audio_b64"])

                # =========================
                # OUTBOUND
                # =========================
                elif t == "outbound_result":
                    orig = data.get("original_text", "").strip()
                    trans = data.get("translated_text", "").strip()
                    is_final = data.get("is_final", True)

                    if not trans or not is_final:
                        continue

                    key = f"{orig}|{trans}"
                    if key == self._last_outbound_final:
                        continue
                    self._last_outbound_final = key

                    print(f"📝 [OUTBOUND] {orig} → {trans}")

                    if self._on_outbound_text:
                        self._on_outbound_text(orig, trans)

                elif t == "error":
                    if self._on_error:
                        self._on_error(data.get("message", "Unknown error"))

            except Exception as e:
                logger.error(f"Receiver error [{direction}]: {e}")