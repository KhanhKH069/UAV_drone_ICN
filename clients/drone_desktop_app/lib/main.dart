import 'dart:convert';
import 'dart:async';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:record/record.dart';
import 'package:http/http.dart' as http;

void main() {
  runApp(const DroneDesktopApp());
}

class DroneDesktopApp extends StatelessWidget {
  const DroneDesktopApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'UAV Dashboard',
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF0F172A),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF38BDF8),
          secondary: Color(0xFFF43F5E),
          surface: Color(0xFF1E293B),
        ),
      ),
      home: const DashboardScreen(),
    );
  }
}

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final String serverHttp = "http://127.0.0.1:8056";
  final String serverWsBase = "ws://127.0.0.1:8765/drone/stream";
  WebSocketChannel? _channel;
  final AudioRecorder _audioRecorder = AudioRecorder();
  StreamSubscription<Uint8List>? _audioStreamSubscription;

  bool _isConnected = false;
  bool _isRecording = false;
  bool _disposed = false;
  bool _isReconnecting = false;

  String _sttText = "Đang xác thực JWT...";
  String _commandJson = "";
  String _telemetryText = "🔋 --% | ⛰️ --m | 📡 -- sats";

  @override
  void initState() {
    super.initState();
    _authenticateAndConnect();
  }

  Future<void> _authenticateAndConnect() async {
    if (_disposed || _isReconnecting) return;
    _isReconnecting = true;
    try {
      final response = await http
          .post(
            Uri.parse("$serverHttp/auth/token"),
            headers: {"Content-Type": "application/json"},
            body: jsonEncode({"client_id": "drone-01", "client_secret": "drone-secret"}),
          )
          .timeout(const Duration(seconds: 5));
      if (!mounted) return;
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final token = data['access_token'];
        setState(() {
          _sttText = "Nhấn giữ nút màu đỏ để nói...";
        });
        _connectWebSocket(token);
      } else {
        setState(() {
          _sttText = "Lỗi xác thực JWT (${response.statusCode})";
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _sttText = "Lỗi kết nối tới Server: $e";
      });
    } finally {
      if (mounted) _isReconnecting = false;
    }
  }

  void _connectWebSocket(String token) {
    try {
      final url = "$serverWsBase?drone_id=UAV-01&lang=vi";
      _channel = WebSocketChannel.connect(Uri.parse(url));
      _channel!.sink.add(jsonEncode({"event": "auth", "token": token}));
      _channel!.stream.listen(
        (message) {
          if (!mounted) return;
          setState(() {
            _isConnected = true;
          });

          try {
            final data = jsonDecode(message);
            final type = data['type'];

            if (type == 'partial') {
              setState(() { _sttText = data['text'] ?? ''; });
            } else if (type == 'command_list') {
              final raw = data['raw_text'] ?? '';
              final commands = data['commands'] as List?;
              setState(() {
                _sttText = "Câu lệnh: $raw";
                if (commands != null) {
                  const encoder = JsonEncoder.withIndent('  ');
                  _commandJson = encoder.convert(commands);
                }
              });
            } else if (type == 'unknown') {
              final raw = data['raw_text'] ?? '';
              setState(() { _sttText = "Không rõ lệnh: $raw"; });
            } else if (type == 'telemetry') {
              final teleData = data['data'];
              if (teleData != null) {
                final bat = teleData['battery'] ?? 0;
                final alt = teleData['alt'] ?? 0.0;
                final sats = teleData['satellites'] ?? 0;
                setState(() {
                  _telemetryText = "🔋 $bat% | ⛰️ ${alt.toStringAsFixed(1)}m | 📡 $sats sats";
                });
              }
            }
          } catch (e) {
            debugPrint("Lỗi parse JSON: $e");
          }
        },
        onError: (error) {
          if (!mounted) return;
          setState(() {
            _isConnected = false;
            _sttText = "Lỗi kết nối Server";
          });
        },
        onDone: () {
          if (!mounted) return;
          setState(() {
            _isConnected = false;
            _sttText = "Server đã ngắt kết nối. Đang kết nối lại...";
          });
          Future.delayed(const Duration(seconds: 3), () {
            if (mounted) _authenticateAndConnect();
          });
        },
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isConnected = false;
        _sttText = "Không thể kết nối WS";
      });
    }
  }

  Future<void> _startRecording() async {
    if (await _audioRecorder.hasPermission()) {
      setState(() {
        _isRecording = true;
        _sttText = "Đang thu âm...";
        _commandJson = "";
      });

      final stream = await _audioRecorder.startStream(const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: 16000,
        numChannels: 1,
      ));

      _audioStreamSubscription = stream.listen((data) {
        if (_channel != null && _isConnected) {
          _channel!.sink.add(data);
        }
      });
    } else {
      setState(() {
        _sttText = "Chưa cấp quyền Microphone!";
      });
    }
  }

  Future<void> _stopRecording() async {
    setState(() {
      _isRecording = false;
      _sttText = "Đang xử lý...";
    });

    await _audioStreamSubscription?.cancel();
    await _audioRecorder.stop();

    if (_channel != null && _isConnected) {
      _channel!.sink.add(jsonEncode({"event": "endpoint"}));
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _audioStreamSubscription?.cancel();
    _audioRecorder.dispose();
    _channel?.sink.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('UAV Controller Dashboard', style: TextStyle(fontWeight: FontWeight.bold)),
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: [
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Row(
              children: [
                Container(
                  width: 12,
                  height: 12,
                  decoration: BoxDecoration(
                    color: _isConnected ? Colors.greenAccent : Colors.redAccent,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 8),
                Text(_isConnected ? 'CONNECTED' : 'DISCONNECTED', 
                  style: TextStyle(
                    color: _isConnected ? Colors.greenAccent : Colors.redAccent,
                    fontWeight: FontWeight.bold,
                  )
                ),
              ],
            ),
          )
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(32.0),
        child: Column(
          children: [
            // Telemetry Bar
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 24),
              margin: const EdgeInsets.only(bottom: 24),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Text(
                _telemetryText,
                style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.cyanAccent),
                textAlign: TextAlign.center,
              ),
            ),
            Expanded(
              flex: 1,
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surface.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: Colors.white12),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Text(
                      "SPEECH RECOGNITION (STT)", 
                      style: TextStyle(color: Colors.grey, letterSpacing: 2)
                    ),
                    const SizedBox(height: 16),
                    Text(
                      _sttText,
                      style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: Colors.white),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 24),
            Expanded(
              flex: 2,
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: const Color(0xFF000000).withValues(alpha: 0.3),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.3)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      "JSON PAYLOAD", 
                      style: TextStyle(color: Colors.grey, letterSpacing: 2)
                    ),
                    const SizedBox(height: 16),
                    Expanded(
                      child: SingleChildScrollView(
                        child: Text(
                          _commandJson.isEmpty ? "{}" : _commandJson,
                          style: const TextStyle(
                            fontFamily: 'Consolas', 
                            fontSize: 16, 
                            color: Colors.greenAccent
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 32),
            GestureDetector(
              onTapDown: (_) => _startRecording(),
              onTapUp: (_) => _stopRecording(),
              onTapCancel: () => _isRecording ? _stopRecording() : null,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 100),
                width: _isRecording ? 140 : 160,
                height: _isRecording ? 140 : 160,
                decoration: BoxDecoration(
                  color: _isRecording ? Theme.of(context).colorScheme.secondary.withValues(alpha: 0.8) : Theme.of(context).colorScheme.secondary,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: Theme.of(context).colorScheme.secondary.withValues(alpha: 0.5),
                      blurRadius: _isRecording ? 30 : 15,
                      spreadRadius: _isRecording ? 10 : 5,
                    )
                  ],
                ),
                child: const Center(
                  child: Text(
                    "PTT",
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 16),
            const Text(
              "HOLD TO SPEAK",
              style: TextStyle(color: Colors.grey, letterSpacing: 2),
            )
          ],
        ),
      ),
    );
  }
}
