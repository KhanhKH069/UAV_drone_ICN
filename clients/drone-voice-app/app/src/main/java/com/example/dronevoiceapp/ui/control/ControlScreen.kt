package com.example.dronevoiceapp.ui.control

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.dronevoiceapp.CommandHistoryItem
import com.example.dronevoiceapp.ConnectionState
import com.example.dronevoiceapp.DroneUiState
import kotlin.math.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ControlScreen(
    uiState: DroneUiState,
    hasAudioPermission: Boolean,
    onPttDown: () -> Unit,
    onPttUp: () -> Unit,
    onSettingsClick: () -> Unit,
    onHistoryClick: () -> Unit = {},
) {
    val pttScale by animateFloatAsState(
        targetValue = if (uiState.isRecording) 0.90f else 1f,
        animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy),
        label = "ptt_scale"
    )

    val connectionColor by animateColorAsState(
        targetValue = when (uiState.connectionState) {
            is ConnectionState.Connected    -> Color(0xFF3FB950)
            is ConnectionState.Connecting   -> Color(0xFFD29922)
            is ConnectionState.Error        -> Color(0xFFFF5252)
            is ConnectionState.Disconnected -> Color(0xFF484F58)
        },
        label = "conn_color"
    )

    val connectionLabel = when (uiState.connectionState) {
        is ConnectionState.Connected    -> "CONNECTED"
        is ConnectionState.Connecting   -> "CONNECTING..."
        is ConnectionState.Error        -> "ERROR"
        is ConnectionState.Disconnected -> "DISCONNECTED"
    }

    val isEnabled = hasAudioPermission && uiState.connectionState is ConnectionState.Connected

    // WER display
    val werText = if (uiState.totalCommands > 0) {
        val wer = (uiState.unknownCommands.toFloat() * 100f / uiState.totalCommands).toInt()
        "WER: $wer%  (${uiState.totalCommands - uiState.unknownCommands}/${uiState.totalCommands})"
    } else "WER: --"

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text("🚁 UAV Controller", fontWeight = FontWeight.Bold, color = Color.White)
                },
                actions = {
                    // Connection dot + label
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.padding(end = 4.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .size(9.dp)
                                .background(connectionColor, CircleShape)
                        )
                        Spacer(Modifier.width(5.dp))
                        Text(
                            connectionLabel,
                            fontSize = 10.sp,
                            color = connectionColor,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 0.5.sp
                        )
                        Spacer(Modifier.width(8.dp))
                    }
                    // History button
                    IconButton(onClick = onHistoryClick, modifier = Modifier.padding(end = 0.dp)) {
                        Icon(Icons.Default.History, contentDescription = "History", tint = Color(0xFF8B949E))
                    }
                    IconButton(onClick = onSettingsClick) {
                        Icon(Icons.Default.Settings, contentDescription = "Settings", tint = Color(0xFF8B949E))
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color(0xFF0D1117))
            )
        },
        containerColor = Color(0xFF0D1117)
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween
        ) {

            // ── Telemetry Card (chi tiết với pitch/roll/yaw) ────────────────
            TelemetryCard(uiState = uiState)

            Spacer(Modifier.height(10.dp))

            // ── STT / Waveform / Command Output ─────────────────────────────
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = Color(0xFF161B22)),
                border = BorderStroke(1.dp, Color(0xFF30363D))
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(16.dp)
                ) {
                    Text(
                        "SPEECH RECOGNITION",
                        fontSize = 10.sp,
                        color = Color(0xFF58A6FF),
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.8.sp
                    )
                    Spacer(Modifier.height(8.dp))

                    // Waveform khi đang ghi, text khi idle
                    if (uiState.isRecording) {
                        AnimatedWaveform(
                            amplitude = uiState.audioAmplitude,
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(56.dp)
                        )
                    } else {
                        Text(uiState.sttText, style = MaterialTheme.typography.titleMedium, color = Color.White)
                    }

                    if (uiState.commandText.isNotEmpty()) {
                        Spacer(Modifier.height(14.dp))
                        HorizontalDivider(color = Color(0xFF30363D))
                        Spacer(Modifier.height(10.dp))
                        Text(
                            "COMMAND PARSED",
                            fontSize = 10.sp,
                            color = Color(0xFF3FB950),
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.8.sp
                        )
                        Spacer(Modifier.height(6.dp))
                        Text(
                            uiState.commandText,
                            style = MaterialTheme.typography.bodyMedium,
                            color = Color(0xFF3FB950),
                            fontFamily = FontFamily.Monospace
                        )
                    }

                    Spacer(Modifier.weight(1f))

                    // Mini command history (3 lệnh gần nhất)
                    if (uiState.commandHistory.isNotEmpty()) {
                        HorizontalDivider(color = Color(0xFF21262D))
                        Spacer(Modifier.height(8.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text("RECENT", fontSize = 9.sp, color = Color(0xFF484F58), letterSpacing = 1.5.sp)
                            Text(werText, fontSize = 9.sp, color = Color(0xFF484F58), fontFamily = FontFamily.Monospace)
                        }
                        Spacer(Modifier.height(4.dp))
                        uiState.commandHistory.take(3).forEach { item ->
                            MiniHistoryRow(item = item)
                        }
                    }
                }
            }

            Spacer(Modifier.height(30.dp))

            // ── PTT Button ───────────────────────────────────────────────────
            Box(contentAlignment = Alignment.Center) {
                // Pulse ring khi đang ghi
                if (uiState.isRecording) {
                    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
                    val pulseScale by infiniteTransition.animateFloat(
                        initialValue = 1f,
                        targetValue = 1.35f,
                        animationSpec = infiniteRepeatable(
                            animation = tween(700, easing = EaseInOut),
                            repeatMode = RepeatMode.Reverse
                        ),
                        label = "pulse"
                    )
                    Box(
                        modifier = Modifier
                            .size(200.dp)
                            .scale(pulseScale)
                            .background(Color(0xFFFF5252).copy(alpha = 0.15f), CircleShape)
                    )
                }

                Button(
                    onClick = {},
                    modifier = Modifier
                        .size(160.dp)
                        .scale(pttScale)
                        .pointerInput(isEnabled) {
                            if (isEnabled) {
                                detectTapGestures(
                                    onPress = {
                                        onPttDown()
                                        tryAwaitRelease()
                                        onPttUp()
                                    }
                                )
                            }
                        },
                    shape = CircleShape,
                    enabled = false,
                    colors = ButtonDefaults.buttonColors(
                        disabledContainerColor = if (uiState.isRecording) Color(0xFFFF5252) else Color(0xFF21262D)
                    ),
                    border = BorderStroke(
                        width = 2.dp,
                        color = when {
                            uiState.isRecording -> Color(0xFFFF5252)
                            isEnabled           -> Color(0xFF58A6FF)
                            else                -> Color(0xFF30363D)
                        }
                    ),
                    elevation = ButtonDefaults.buttonElevation(0.dp)
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            "PTT",
                            fontSize = 26.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = when {
                                uiState.isRecording -> Color.White
                                isEnabled           -> Color(0xFF58A6FF)
                                else                -> Color(0xFF484F58)
                            }
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            text = when {
                                uiState.isRecording                                              -> "Đang ghi..."
                                !hasAudioPermission                                              -> "Cần quyền mic"
                                uiState.connectionState !is ConnectionState.Connected            -> "Offline"
                                else                                                             -> "Giữ để nói"
                            },
                            fontSize = 11.sp,
                            color = if (uiState.isRecording) Color.White.copy(alpha = 0.75f) else Color(0xFF484F58)
                        )
                    }
                }
            }

            Spacer(Modifier.height(20.dp))

            // ── Footer ───────────────────────────────────────────────────────
            Text(
                "${uiState.serverIp}:${uiState.serverPort}  |  ${uiState.droneId}",
                fontSize = 11.sp,
                color = Color(0xFF484F58),
                fontFamily = FontFamily.Monospace
            )
            Spacer(Modifier.height(4.dp))
        }
    }
}

// ─── Telemetry Card (chi tiết) ────────────────────────────────────────────────

@Composable
fun TelemetryCard(uiState: DroneUiState) {
    val t = uiState.telemetry
    val bat   = t["battery"]?.toInt() ?: 0
    val alt   = t["alt"] ?: 0.0
    val sats  = t["satellites"]?.toInt() ?: 0
    val pitch = t["pitch"] ?: 0.0
    val roll  = t["roll"] ?: 0.0
    val yaw   = t["yaw"] ?: 0.0

    // Màu pin
    val batColor = when {
        bat > 50 -> Color(0xFF3FB950)
        bat > 20 -> Color(0xFFD29922)
        else     -> Color(0xFFFF5252)
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF161B22)),
        border = BorderStroke(1.dp, Color(0xFF30363D))
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text("TELEMETRY", fontSize = 10.sp, color = Color(0xFF58A6FF), fontWeight = FontWeight.Bold, letterSpacing = 1.8.sp)
            Spacer(Modifier.height(8.dp))

            // Row 1: Battery + Altitude + Satellites
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                TelemetryItem(label = "BAT", value = "$bat%", valueColor = batColor)
                TelemetryItem(label = "ALT", value = "${"%.1f".format(alt)}m", valueColor = Color.White)
                TelemetryItem(label = "GPS", value = "$sats sats",
                    valueColor = if (sats >= 6) Color(0xFF3FB950) else if (sats >= 4) Color(0xFFD29922) else Color(0xFFFF5252))
            }

            Spacer(Modifier.height(8.dp))

            // Row 2: Pitch + Roll + Yaw attitude indicators
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                AttitudeItem(label = "PITCH", valueDeg = Math.toDegrees(pitch))
                AttitudeItem(label = "ROLL",  valueDeg = Math.toDegrees(roll))
                AttitudeItem(label = "YAW",   valueDeg = Math.toDegrees(yaw))
            }
        }
    }
}

@Composable
fun TelemetryItem(label: String, value: String, valueColor: Color = Color.White) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, fontSize = 9.sp, color = Color(0xFF484F58), letterSpacing = 1.sp)
        Spacer(Modifier.height(2.dp))
        Text(value, fontSize = 15.sp, fontWeight = FontWeight.Bold, color = valueColor, fontFamily = FontFamily.Monospace)
    }
}

@Composable
fun AttitudeItem(label: String, valueDeg: Double) {
    val color = if (abs(valueDeg) < 5) Color(0xFF3FB950) else if (abs(valueDeg) < 15) Color(0xFFD29922) else Color(0xFFFF5252)
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, fontSize = 9.sp, color = Color(0xFF484F58), letterSpacing = 1.sp)
        Spacer(Modifier.height(2.dp))
        Text(
            "${if (valueDeg >= 0) "+" else ""}${"%.1f".format(valueDeg)}°",
            fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
            color = color, fontFamily = FontFamily.Monospace
        )
    }
}

// ─── Animated Waveform ────────────────────────────────────────────────────────

@Composable
fun AnimatedWaveform(amplitude: Float, modifier: Modifier = Modifier) {
    // Smooth animated amplitude
    val animatedAmplitude by animateFloatAsState(
        targetValue = amplitude,
        animationSpec = spring(stiffness = Spring.StiffnessMedium),
        label = "waveform_amp"
    )

    // Infinite time for waveform movement
    val infiniteTransition = rememberInfiniteTransition(label = "wave_time")
    val timeOffset by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 2f * PI.toFloat(),
        animationSpec = infiniteRepeatable(
            animation = tween(1200, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "wave_time_val"
    )

    Canvas(modifier = modifier) {
        val w = size.width
        val h = size.height
        val midY = h / 2f
        val barCount = 28
        val barWidth = w / (barCount * 2f)
        val maxBarH = h * 0.85f

        for (i in 0 until barCount) {
            val x = i * (w / barCount.toFloat()) + barWidth / 2
            // Sine wave phase offset creates rolling wave effect
            val phase = i.toFloat() / barCount * 2f * PI.toFloat() + timeOffset
            val sinVal = sin(phase) * 0.4f + 0.6f  // 0.2..1.0
            val barH = maxBarH * animatedAmplitude.coerceAtLeast(0.05f) * sinVal
            val alpha = 0.5f + 0.5f * sinVal

            drawRoundRect(
                color = Color(0xFF58A6FF).copy(alpha = alpha),
                topLeft = Offset(x - barWidth / 2, midY - barH / 2),
                size = Size(barWidth, barH),
                cornerRadius = CornerRadius(barWidth / 2)
            )
        }
    }
}

// ─── Mini History Row ─────────────────────────────────────────────────────────

@Composable
fun MiniHistoryRow(item: CommandHistoryItem) {
    val (color, prefix) = when (item.type) {
        "command" -> Pair(Color(0xFF3FB950), "✓")
        "unknown" -> Pair(Color(0xFFD29922), "?")
        else      -> Pair(Color(0xFFFF5252), "✗")
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 1.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Text(prefix, fontSize = 10.sp, color = color, fontWeight = FontWeight.Bold)
        Text(
            "[${item.timestamp}]",
            fontSize = 9.sp,
            color = Color(0xFF484F58),
            fontFamily = FontFamily.Monospace
        )
        Text(
            item.rawText.take(28),
            fontSize = 10.sp,
            color = Color(0xFF8B949E),
            modifier = Modifier.weight(1f)
        )
        Text(
            item.intent.take(16),
            fontSize = 9.sp,
            color = color,
            fontFamily = FontFamily.Monospace
        )
    }
}
