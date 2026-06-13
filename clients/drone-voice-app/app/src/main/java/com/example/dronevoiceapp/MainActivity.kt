package com.example.dronevoiceapp

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.animation.Crossfade
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.dronevoiceapp.theme.DroneVoiceAppTheme
import com.example.dronevoiceapp.ui.control.ControlScreen
import com.example.dronevoiceapp.ui.history.CommandHistoryScreen
import com.example.dronevoiceapp.ui.settings.SettingsScreen

enum class Screen { Control, Settings, History }

class MainActivity : ComponentActivity() {

    private val viewModel: DroneViewModel by viewModels()

    private var hasAudioPermission by mutableStateOf(false)

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        hasAudioPermission = isGranted
        if (isGranted) {
            viewModel.connect()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Check permission & connect
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            hasAudioPermission = true
            viewModel.connect()
        } else {
            requestPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }

        setContent {
            DroneVoiceAppTheme(darkTheme = true) { // Force Dark Mode for this app
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
                    var currentScreen by remember { mutableStateOf(Screen.Control) }

                    Crossfade(targetState = currentScreen, label = "screen_transition") { screen ->
                        when (screen) {
                            Screen.Control -> {
                                ControlScreen(
                                    uiState = uiState,
                                    hasAudioPermission = hasAudioPermission,
                                    onPttDown = { viewModel.startRecording(hasAudioPermission) },
                                    onPttUp = { viewModel.stopRecording() },
                                    onSettingsClick = { currentScreen = Screen.Settings },
                                    onHistoryClick = { currentScreen = Screen.History }
                                )
                            }
                            Screen.Settings -> {
                                SettingsScreen(
                                    uiState = uiState,
                                    onSave = { ip, port, clientId, secret, droneId, useTls ->
                                        viewModel.saveSettings(ip, port, clientId, secret, droneId, useTls)
                                        viewModel.connect() // Reconnect with new settings
                                        currentScreen = Screen.Control
                                    },
                                    onBack = { currentScreen = Screen.Control }
                                )
                            }
                            Screen.History -> {
                                CommandHistoryScreen(
                                    uiState = uiState,
                                    onBack = { currentScreen = Screen.Control },
                                    onClear = { viewModel.clearHistory() }
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
