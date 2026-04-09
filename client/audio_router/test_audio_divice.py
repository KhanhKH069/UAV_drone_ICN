from audio_manager import AudioManager

audio_manager = AudioManager()
audio_manager.play_tts("Hello, how are you?")
audio_manager.list_devices()
# if audio_manager._find_device("pulse"):
#     print("pulse found")
# else:
#     print("pulse not found")

