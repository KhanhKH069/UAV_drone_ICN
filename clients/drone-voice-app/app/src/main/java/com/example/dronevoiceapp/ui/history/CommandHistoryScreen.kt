package com.example.dronevoiceapp.ui.history

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.DeleteSweep
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.dronevoiceapp.CommandHistoryItem
import com.example.dronevoiceapp.DroneUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CommandHistoryScreen(
    uiState: DroneUiState,
    onBack: () -> Unit,
    onClear: () -> Unit,
) {
    val totalCommands = uiState.totalCommands
    val unknownCount = uiState.unknownCommands
    val recognizedCount = totalCommands - unknownCount
    val werPct = if (totalCommands > 0) (unknownCount.toFloat() * 100f / totalCommands).toInt() else 0

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("📋 Command History", fontWeight = FontWeight.Bold, color = Color.White, fontSize = 17.sp)
                        Text(
                            "WER: $werPct%  |  $recognizedCount/$totalCommands nhận diện",
                            fontSize = 11.sp,
                            color = Color(0xFF8B949E),
                            fontFamily = FontFamily.Monospace
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back", tint = Color.White)
                    }
                },
                actions = {
                    if (uiState.commandHistory.isNotEmpty()) {
                        IconButton(onClick = onClear) {
                            Icon(Icons.Default.DeleteSweep, contentDescription = "Clear", tint = Color(0xFFFF5252))
                        }
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
        ) {
            // ── Stats Banner ─────────────────────────────────────────────────
            if (totalCommands > 0) {
                StatsBanner(
                    total = totalCommands,
                    recognized = recognizedCount,
                    unknown = unknownCount,
                    werPct = werPct
                )
            }

            // ── History List ─────────────────────────────────────────────────
            if (uiState.commandHistory.isEmpty()) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("🎙️", fontSize = 48.sp)
                        Spacer(Modifier.height(16.dp))
                        Text(
                            "Chưa có lệnh nào",
                            color = Color(0xFF484F58),
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Medium
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            "Nhấn giữ PTT và nói lệnh điều khiển",
                            color = Color(0xFF30363D),
                            fontSize = 13.sp
                        )
                    }
                }
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    contentPadding = PaddingValues(top = 12.dp, bottom = 24.dp)
                ) {
                    itemsIndexed(uiState.commandHistory) { index, item ->
                        HistoryCard(index = index, item = item)
                    }
                }
            }
        }
    }
}

// ─── Stats Banner ─────────────────────────────────────────────────────────────

@Composable
fun StatsBanner(total: Int, recognized: Int, unknown: Int, werPct: Int) {
    val werColor = when {
        werPct <= 10 -> Color(0xFF3FB950)
        werPct <= 25 -> Color(0xFFD29922)
        else         -> Color(0xFFFF5252)
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color(0xFF161B22))
            .padding(horizontal = 20.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.SpaceEvenly,
        verticalAlignment = Alignment.CenterVertically
    ) {
        StatItem(label = "TỔNG", value = total.toString(), color = Color(0xFF58A6FF))
        StatDivider()
        StatItem(label = "NHẬN DIỆN", value = recognized.toString(), color = Color(0xFF3FB950))
        StatDivider()
        StatItem(label = "UNKNOWN", value = unknown.toString(), color = Color(0xFFD29922))
        StatDivider()
        StatItem(label = "WER", value = "$werPct%", color = werColor)
    }

    // WER Progress bar
    val progress = recognized.toFloat() / total.toFloat()
    LinearProgressIndicator(
        progress = { progress },
        modifier = Modifier.fillMaxWidth().height(3.dp),
        color = Color(0xFF3FB950),
        trackColor = Color(0xFFFF5252),
    )
}

@Composable
fun StatItem(label: String, value: String, color: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            value,
            fontSize = 22.sp,
            fontWeight = FontWeight.ExtraBold,
            color = color,
            fontFamily = FontFamily.Monospace
        )
        Text(label, fontSize = 9.sp, color = Color(0xFF484F58), letterSpacing = 1.sp)
    }
}

@Composable
fun StatDivider() {
    Box(
        modifier = Modifier
            .height(32.dp)
            .width(1.dp)
            .background(Color(0xFF30363D))
    )
}

// ─── History Card ─────────────────────────────────────────────────────────────

@Composable
fun HistoryCard(index: Int, item: CommandHistoryItem) {
    val (borderColor, badgeBg, badgeText) = when (item.type) {
        "command" -> Triple(Color(0xFF238636), Color(0xFF238636).copy(alpha = 0.2f), "✓ NHẬN DIỆN")
        "unknown" -> Triple(Color(0xFF9E6A03), Color(0xFF9E6A03).copy(alpha = 0.2f), "? UNKNOWN")
        else      -> Triple(Color(0xFFDA3633), Color(0xFFDA3633).copy(alpha = 0.2f), "✗ LỖI")
    }
    val textColor = when (item.type) {
        "command" -> Color(0xFF3FB950)
        "unknown" -> Color(0xFFD29922)
        else      -> Color(0xFFFF5252)
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(10.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFF161B22)),
        border = BorderStroke(1.dp, borderColor.copy(alpha = 0.4f))
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // Header row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Badge
                Box(
                    modifier = Modifier
                        .background(badgeBg, RoundedCornerShape(4.dp))
                        .padding(horizontal = 6.dp, vertical = 2.dp)
                ) {
                    Text(badgeText, fontSize = 9.sp, color = textColor, fontWeight = FontWeight.Bold, letterSpacing = 0.5.sp)
                }

                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    if (item.confidence > 0) {
                        Text(
                            "${item.confidence}%",
                            fontSize = 11.sp,
                            color = Color(0xFF484F58),
                            fontFamily = FontFamily.Monospace
                        )
                    }
                    Text(
                        item.timestamp,
                        fontSize = 10.sp,
                        color = Color(0xFF484F58),
                        fontFamily = FontFamily.Monospace
                    )
                }
            }

            Spacer(Modifier.height(8.dp))

            // Raw text
            Text(
                "\"${item.rawText}\"",
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium,
                color = Color.White
            )

            Spacer(Modifier.height(4.dp))

            // Intent
            if (item.intent.isNotEmpty() && item.intent != "unknown") {
                Text(
                    "→ ${item.intent}",
                    fontSize = 12.sp,
                    color = textColor,
                    fontFamily = FontFamily.Monospace
                )
            }
        }
    }
}
