package com.example.dronevoiceapp.ui.settings

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.dronevoiceapp.DroneUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    uiState: DroneUiState,
    onSave: (ip: String, port: String, clientId: String, secret: String, droneId: String, useTls: Boolean) -> Unit,
    onBack: () -> Unit,
) {
    var serverIp     by remember { mutableStateOf(uiState.serverIp) }
    var serverPort   by remember { mutableStateOf(uiState.serverPort) }
    var clientId     by remember { mutableStateOf(uiState.clientId) }
    var clientSecret by remember { mutableStateOf(uiState.clientSecret) }
    var droneId      by remember { mutableStateOf(uiState.droneId) }
    var useTls       by remember { mutableStateOf(uiState.useTls) }
    var secretVisible by remember { mutableStateOf(false) }

    fun doSave() = onSave(serverIp.trim(), serverPort.trim(), clientId.trim(), clientSecret.trim(), droneId.trim(), useTls)

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("⚙️ Settings", fontWeight = FontWeight.Bold, color = Color.White) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back", tint = Color.White)
                    }
                },
                actions = {
                    IconButton(onClick = ::doSave) {
                        Icon(Icons.Default.Check, contentDescription = "Save", tint = Color(0xFF3FB950))
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
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(20.dp)
        ) {

            // ── Server ───────────────────────────────────────────────────────
            SettingsSection(title = "SERVER") {
                DroneTextField("IP Address", serverIp, { serverIp = it }, KeyboardType.Uri)
                DroneTextField("HTTP Port (mặc định: 8056)", serverPort, { serverPort = it }, KeyboardType.Number)
                
                Row(
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
                ) {
                    Text("Sử dụng TLS (wss://)", color = Color.White)
                    Switch(
                        checked = useTls,
                        onCheckedChange = { useTls = it },
                        colors = SwitchDefaults.colors(checkedThumbColor = Color(0xFF3FB950), checkedTrackColor = Color(0xFF238636))
                    )
                }
            }

            // ── Auth ─────────────────────────────────────────────────────────
            SettingsSection(title = "AUTHENTICATION") {
                DroneTextField("Client ID (mặc định: drone-01)", clientId, { clientId = it })
                OutlinedTextField(
                    value = clientSecret,
                    onValueChange = { clientSecret = it },
                    label = { Text("Client Secret") },
                    modifier = Modifier.fillMaxWidth(),
                    visualTransformation = if (secretVisible) VisualTransformation.None else PasswordVisualTransformation(),
                    trailingIcon = {
                        IconButton(onClick = { secretVisible = !secretVisible }) {
                            Icon(
                                imageVector = if (secretVisible) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                                contentDescription = if (secretVisible) "Ẩn" else "Hiện",
                                tint = Color(0xFF8B949E)
                            )
                        }
                    },
                    colors = droneTextFieldColors()
                )
            }

            // ── Drone ─────────────────────────────────────────────────────────
            SettingsSection(title = "DRONE") {
                DroneTextField("Drone ID (mặc định: UAV-01)", droneId, { droneId = it })
            }

            Spacer(Modifier.height(8.dp))

            // ── Save Button ───────────────────────────────────────────────────
            Button(
                onClick = ::doSave,
                modifier = Modifier.fillMaxWidth().height(52.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF238636)),
                shape = RoundedCornerShape(10.dp)
            ) {
                Text("💾  Lưu & Kết Nối Lại", fontWeight = FontWeight.Bold, fontSize = 15.sp)
            }

            Spacer(Modifier.height(16.dp))
        }
    }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

@Composable
fun SettingsSection(title: String, content: @Composable ColumnScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(title, fontSize = 10.sp, color = Color(0xFF58A6FF), fontWeight = FontWeight.Bold, letterSpacing = 1.8.sp)
        Card(
            shape = RoundedCornerShape(12.dp),
            colors = CardDefaults.cardColors(containerColor = Color(0xFF161B22))
        ) {
            Column(
                modifier = Modifier.fillMaxWidth().padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                content = content
            )
        }
    }
}

@Composable
fun DroneTextField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    keyboardType: KeyboardType = KeyboardType.Text,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        modifier = Modifier.fillMaxWidth(),
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
        colors = droneTextFieldColors()
    )
}

@Composable
fun droneTextFieldColors() = OutlinedTextFieldDefaults.colors(
    focusedTextColor    = Color.White,
    unfocusedTextColor  = Color.White,
    focusedLabelColor   = Color(0xFF58A6FF),
    unfocusedLabelColor = Color(0xFF8B949E),
    focusedBorderColor  = Color(0xFF58A6FF),
    unfocusedBorderColor = Color(0xFF30363D),
    cursorColor         = Color(0xFF58A6FF),
)
