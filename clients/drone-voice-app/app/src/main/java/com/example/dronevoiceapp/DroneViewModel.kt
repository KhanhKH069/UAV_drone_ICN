package com.example.dronevoiceapp

import android.app.Application
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

sealed class ConnectionState {
    object Disconnected : ConnectionState()
    object Connecting : ConnectionState()
    object Connected : ConnectionState()
    data class Error(val message: String) : ConnectionState()
}

data class CommandHistoryItem(
    val timestamp: String,
    val rawText: String,
    val intent: String,
    val confidence: Int,
    val type: String, // "command", "unknown", "error"
)

data class DroneUiState(
    val connectionState: ConnectionState = ConnectionState.Disconnected,
    val sttText: String = "Chưa kết nối",
    val commandText: String = "",
    val telemetryText: String = "🔋 --% | ⛰️ --m | 📡 -- sats",
    val telemetry: Map<String, Double> = emptyMap(), // dữ liệu telemetry đầy đủ (pitch, roll, yaw...)
    val isRecording: Boolean = false,
    val audioAmplitude: Float = 0f, // 0f..1f RMS amplitude cho waveform
    val serverIp: String = "192.168.1.100",
    val serverPort: String = "8056",
    val clientId: String = "drone-01",
    val clientSecret: String = "",
    val droneId: String = "UAV-01",
    val useTls: Boolean = false,
    val commandHistory: List<CommandHistoryItem> = emptyList(),
    val totalCommands: Int = 0,
    val unknownCommands: Int = 0, // để tính WER
)

class DroneViewModel(application: Application) : AndroidViewModel(application) {

    private val prefs = application.getSharedPreferences("drone_prefs", Context.MODE_PRIVATE)

    private val _uiState = MutableStateFlow(
        DroneUiState(
            serverIp = prefs.getString("server_ip", "192.168.1.100") ?: "192.168.1.100",
            serverPort = prefs.getString("server_port", "8056") ?: "8056",
            clientId = prefs.getString("client_id", "drone-01") ?: "drone-01",
            clientSecret = prefs.getString("client_secret", "") ?: "",
            droneId = prefs.getString("drone_id", "UAV-01") ?: "UAV-01",
            useTls = prefs.getBoolean("use_tls", false),
        )
    )
    val uiState: StateFlow<DroneUiState> = _uiState.asStateFlow()

    private val httpClient = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .connectTimeout(10, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private var audioRecord: AudioRecord? = null
    private var isRecordingInternal = false
    private var recordingThread: Thread? = null
    private var reconnectJob: Job? = null

    // ─── Settings ────────────────────────────────────────────────────────────

    fun saveSettings(ip: String, port: String, clientId: String, clientSecret: String, droneId: String, useTls: Boolean) {
        prefs.edit()
            .putString("server_ip", ip)
            .putString("server_port", port)
            .putString("client_id", clientId)
            .putString("client_secret", clientSecret)
            .putString("drone_id", droneId)
            .putBoolean("use_tls", useTls)
            .apply()
        _uiState.update {
            it.copy(
                serverIp = ip,
                serverPort = port,
                clientId = clientId,
                clientSecret = clientSecret,
                droneId = droneId,
                useTls = useTls,
            )
        }
    }

    fun clearHistory() {
        _uiState.update { it.copy(commandHistory = emptyList(), totalCommands = 0, unknownCommands = 0) }
    }

    // ─── Connection ───────────────────────────────────────────────────────────

    fun connect() {
        reconnectJob?.cancel()
        reconnectJob = viewModelScope.launch { connectWithRetry() }
    }

    private suspend fun connectWithRetry() {
        var delayMs = 2000L
        while (true) {
            _uiState.update { it.copy(connectionState = ConnectionState.Connecting, sttText = "Đang kết nối...") }
            val ok = authenticate()
            if (ok) return          // WebSocket listener will call scheduleReconnect() if it drops
            _uiState.update { it.copy(connectionState = ConnectionState.Error("Kết nối thất bại"), sttText = "Thử lại sau ${delayMs / 1000}s...") }
            delay(delayMs)
            delayMs = minOf(delayMs * 2, 30_000L)
        }
    }

    private suspend fun authenticate(): Boolean = suspendCancellableCoroutine { cont ->
        val s = _uiState.value
        if (s.clientSecret.isBlank()) {
            _uiState.update { it.copy(connectionState = ConnectionState.Error("Chưa cấu hình"), sttText = "Vào ⚙️ Settings để nhập Client Secret") }
            cont.resume(false) {}
            return@suspendCancellableCoroutine
        }
        val body = """{"client_id":"${s.clientId}","client_secret":"${s.clientSecret}"}"""
            .toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url("http://${s.serverIp}:${s.serverPort}/auth/token")
            .post(body)
            .build()
        val call = httpClient.newCall(request)
        cont.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                Log.e("DroneVM", "Auth failed: ${e.message}")
                cont.resume(false) {}
            }
            override fun onResponse(call: Call, response: Response) {
                if (response.isSuccessful) {
                    val token = runCatching {
                        JSONObject(response.body?.string() ?: "{}").optString("access_token")
                    }.getOrElse { "" }
                    openWebSocket(token)
                    cont.resume(true) {}
                } else {
                    Log.e("DroneVM", "Auth HTTP ${response.code}")
                    cont.resume(false) {}
                }
            }
        })
    }

    private fun openWebSocket(token: String) {
        val s = _uiState.value
        val protocol = if (s.useTls) "wss" else "ws"
        val url = "$protocol://${s.serverIp}:${s.serverPort}/drone/stream?token=$token&drone_id=${s.droneId}&lang=vi"
        webSocket = httpClient.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                _uiState.update { it.copy(connectionState = ConnectionState.Connected, sttText = "Nhấn giữ PTT để nói...") }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                runCatching {
                    val json = JSONObject(text)
                    val now = java.time.LocalTime.now().format(java.time.format.DateTimeFormatter.ofPattern("HH:mm:ss"))

                    when (json.optString("type")) {
                        "partial" -> _uiState.update { it.copy(sttText = "🎤 ${json.optString("text")}") }
                        "command" -> {
                            val intent = json.optString("intent")
                            val conf = json.optInt("confidence", 0)
                            val raw = json.optString("raw_text")
                            val historyItem = CommandHistoryItem(
                                timestamp = now,
                                rawText = raw,
                                intent = intent,
                                confidence = conf,
                                type = "command"
                            )
                            _uiState.update {
                                val newHistory = (listOf(historyItem) + it.commandHistory).take(100)
                                it.copy(
                                    sttText = "✅ \"$raw\"",
                                    commandText = "→ $intent  (conf: $conf%)",
                                    commandHistory = newHistory,
                                    totalCommands = it.totalCommands + 1
                                )
                            }
                        }
                        "command_list" -> {
                            val raw = json.optString("raw_text")
                            val cmds = json.optJSONArray("commands")?.toString(2) ?: "[]"
                            val historyItem = CommandHistoryItem(
                                timestamp = now,
                                rawText = raw,
                                intent = "[multi-command]",
                                confidence = 0,
                                type = "command"
                            )
                            _uiState.update {
                                val newHistory = (listOf(historyItem) + it.commandHistory).take(100)
                                it.copy(
                                    sttText = "✅ \"$raw\"",
                                    commandText = cmds,
                                    commandHistory = newHistory,
                                    totalCommands = it.totalCommands + 1
                                )
                            }
                        }
                        "unknown" -> {
                            val raw = json.optString("raw_text")
                            val historyItem = CommandHistoryItem(
                                timestamp = now,
                                rawText = raw,
                                intent = "unknown",
                                confidence = 0,
                                type = "unknown"
                            )
                            _uiState.update {
                                val newHistory = (listOf(historyItem) + it.commandHistory).take(100)
                                it.copy(
                                    sttText = "❓ Không rõ: \"$raw\"",
                                    commandText = "",
                                    commandHistory = newHistory,
                                    totalCommands = it.totalCommands + 1,
                                    unknownCommands = it.unknownCommands + 1
                                )
                            }
                        }
                        "telemetry" -> json.optJSONObject("data")?.let { data ->
                            val bat  = data.optInt("battery", 0)
                            val alt  = data.optDouble("alt", 0.0)
                            val sats = data.optInt("satellites", 0)
                            val pitch = data.optDouble("pitch", 0.0)
                            val roll  = data.optDouble("roll", 0.0)
                            val yaw   = data.optDouble("yaw", 0.0)
                            val telemetryMap = mapOf(
                                "battery" to bat.toDouble(),
                                "alt" to alt,
                                "satellites" to sats.toDouble(),
                                "pitch" to pitch,
                                "roll" to roll,
                                "yaw" to yaw,
                            )
                            _uiState.update {
                                it.copy(
                                    telemetryText = "🔋 $bat% | ⛰️ ${"%.1f".format(alt)}m | 📡 $sats sats",
                                    telemetry = telemetryMap
                                )
                            }
                        }
                    }
                }.onFailure { Log.e("DroneVM", "WS parse error", it) }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                _uiState.update { it.copy(connectionState = ConnectionState.Disconnected, sttText = "Mất kết nối. Đang thử lại...") }
                scheduleReconnect(2000L)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e("DroneVM", "WS failure", t)
                _uiState.update { it.copy(connectionState = ConnectionState.Error(t.message ?: "Lỗi không xác định"), sttText = "Lỗi: ${t.message}") }
                scheduleReconnect(3000L)
            }
        })
    }

    private fun scheduleReconnect(delayMs: Long = 3000L) {
        reconnectJob?.cancel()
        reconnectJob = viewModelScope.launch {
            delay(delayMs)
            connectWithRetry()
        }
    }

    fun disconnect() {
        reconnectJob?.cancel()
        webSocket?.close(1000, "User disconnected")
        webSocket = null
        _uiState.update { it.copy(connectionState = ConnectionState.Disconnected, sttText = "Đã ngắt kết nối") }
    }

    // ─── Recording ────────────────────────────────────────────────────────────

    fun startRecording(hasPermission: Boolean) {
        if (!hasPermission || isRecordingInternal) return
        if (_uiState.value.connectionState !is ConnectionState.Connected) return
        val sampleRate = 16000
        val bufferSize = AudioRecord.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        @Suppress("MissingPermission")
        audioRecord = AudioRecord(MediaRecorder.AudioSource.MIC, sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, bufferSize)
        audioRecord?.startRecording()
        isRecordingInternal = true
        _uiState.update { it.copy(isRecording = true, sttText = "🔴 Đang thu âm...", commandText = "", audioAmplitude = 0f) }
        recordingThread = Thread {
            val buffer = ByteArray(bufferSize)
            while (isRecordingInternal) {
                val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0
                if (read > 1) {  // Nhàn cần ít nhất 2 byte (1 sample int16)
                    webSocket?.send(buffer.copyOf(read).toByteString())
                    // Tính RMS amplitude để drive waveform animation
                    val sampleCount = read / 2  // số samples int16 (mỗi sample = 2 byte)
                    var sumSq = 0.0
                    for (i in 0 until sampleCount) {
                        val b0 = buffer[i * 2].toInt() and 0xFF
                        val b1 = buffer[i * 2 + 1].toInt()
                        val sample = (b1 shl 8 or b0).toShort()
                        val norm = sample.toDouble() / 32768.0
                        sumSq += norm * norm
                    }
                    val rms = Math.sqrt(sumSq / sampleCount).toFloat().coerceIn(0f, 1f)
                    _uiState.update { it.copy(audioAmplitude = rms) }
                }
            }
            // Reset amplitude khi dừng
            _uiState.update { it.copy(audioAmplitude = 0f) }
        }.also { it.start() }
    }

    fun stopRecording() {
        if (!isRecordingInternal) return
        isRecordingInternal = false
        
        try {
            recordingThread?.join(500)
        } catch (e: InterruptedException) {
            Log.w("DroneVM", "recordingThread join interrupted")
        }
        recordingThread = null
        
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
        webSocket?.send(JSONObject().apply { put("event", "endpoint") }.toString())
        _uiState.update { it.copy(isRecording = false, sttText = "⏳ Đang xử lý...") }
    }

    override fun onCleared() {
        super.onCleared()
        stopRecording()
        disconnect()
        httpClient.dispatcher.executorService.shutdown()
    }
}
