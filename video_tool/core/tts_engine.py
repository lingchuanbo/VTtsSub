import os


class TTSEngine:
    def __init__(self, engine_type="ttsfm", api_key=None, api_url=None):
        """
        Initialize TTS Engine.
        
        Args:
            engine_type (str): "ttsfm", "elevenlabs", or "qwen"
            api_key (str): API key (required for elevenlabs and qwen)
            api_url (str): API URL for Qwen (optional)
        """
        self.engine_type = engine_type
        self.api_key = api_key
        self.api_url = api_url or "https://dashscope-intl.aliyuncs.com/api/v1"

    def generate_audio(self, text, output_path, voice="alloy", model_id=None, language_type="Chinese", speed=1.0):
        """
        Generates audio from text using selected TTS engine.
        
        Args:
            text (str): Text to convert to speech.
            output_path (str): Path to save the audio file.
            voice (str): Voice ID to use.
            model_id (str): Model ID for ElevenLabs or Qwen
            language_type (str): Language type for Qwen
            speed (float): Speech speed (TTSFM only, 0.25-4.0)
        """
        if not text or not text.strip():
            raise ValueError("文本不能为空")
        
        try:
            if self.engine_type == "elevenlabs":
                self._generate_elevenlabs(text, output_path, voice, model_id)
            elif self.engine_type == "qwen":
                self._generate_qwen(text, output_path, voice, model_id, language_type)
            else:
                self._generate_ttsfm(text, output_path, voice, speed)
            
            # Verify file was created
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise RuntimeError("TTS 生成失败：未生成音频文件")
            
            return True
        except Exception as e:
            print(f"Error generating TTS: {e}")
            raise

    def _generate_ttsfm(self, text, output_path, voice, speed=1.0):
        """Generate audio using TTSFM."""
        from ttsfm import TTSClient, AudioFormat, Voice
        
        # Add ffmpeg to PATH if available locally
        core_dir = os.path.dirname(__file__)
        ffmpeg_path = os.path.join(core_dir, 'ffmpeg.exe')
        if os.path.exists(ffmpeg_path):
            os.environ['PATH'] = core_dir + os.pathsep + os.environ.get('PATH', '')
        
        # Map voice string to Voice enum
        voice_map = {
            "alloy": Voice.ALLOY,
            "echo": Voice.ECHO,
            "fable": Voice.FABLE,
            "onyx": Voice.ONYX,
            "nova": Voice.NOVA,
            "shimmer": Voice.SHIMMER,
        }
        
        voice_enum = voice_map.get(voice.lower(), Voice.ALLOY)
        
        # Ensure speed is float
        speed = float(speed)
        print(f"TTSFM: voice={voice}, speed={speed}")
        
        client = TTSClient()
        
        # Generate speech with speed parameter
        # Note: speed adjustment requires ffmpeg to be installed
        try:
            response = client.generate_speech(
                text=text,
                voice=voice_enum,
                response_format=AudioFormat.MP3,
                speed=speed
            )
        except TypeError:
            # If speed parameter not supported, generate without it
            print("Warning: speed parameter not supported, using default speed")
            response = client.generate_speech(
                text=text,
                voice=voice_enum,
                response_format=AudioFormat.MP3
            )
        
        # Save to file (remove .mp3 extension if present, as save_to_file adds it)
        base_path = output_path
        if output_path.lower().endswith('.mp3'):
            base_path = output_path[:-4]
        
        response.save_to_file(base_path)
        
        # Ensure the file exists at the expected path
        expected_path = base_path + ".mp3"
        if expected_path != output_path and os.path.exists(expected_path):
            os.rename(expected_path, output_path)

    def _generate_elevenlabs(self, text, output_path, voice_id, model_id):
        """Generate audio using ElevenLabs API."""
        from elevenlabs.client import ElevenLabs
        
        if not self.api_key:
            raise ValueError("ElevenLabs API key is required")
        
        client = ElevenLabs(api_key=self.api_key)
        
        audio_generator = client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=model_id or "eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        
        with open(output_path, "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)
    
    def _generate_qwen(self, text, output_path, voice, model_id, language_type):
        """Generate audio using Qwen TTS API (DashScope)."""
        import dashscope
        import base64
        
        if not self.api_key:
            raise ValueError("Qwen API key is required")
        
        dashscope.base_http_api_url = self.api_url
        
        response = dashscope.MultiModalConversation.call(
            model=model_id or "qwen3-tts-flash",
            api_key=self.api_key,
            text=text,
            voice=voice,
            language_type=language_type,
            stream=False
        )
        
        if response.status_code == 200:
            if hasattr(response.output, 'audio'):
                audio_data = response.output.audio
                if isinstance(audio_data, str):
                    audio_bytes = base64.b64decode(audio_data)
                else:
                    audio_bytes = audio_data
                
                with open(output_path, "wb") as f:
                    f.write(audio_bytes)
            else:
                raise ValueError(f"No audio data in response: {response}")
        else:
            raise ValueError(f"Qwen TTS API error: {response.message}")

    def get_ttsfm_voices(self):
        """Returns TTSFM voices."""
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    def get_elevenlabs_voices(self):
        """Returns popular ElevenLabs voice IDs."""
        return [
            ("Rachel", "21m00Tcm4TlvDq8ikWAM"),
            ("Domi", "AZnzlk1XvdvUeBnXmlld"),
            ("Bella", "EXAVITQu4vr4xnSDxMaL"),
            ("Antoni", "ErXwobaYiN019PkySvjV"),
            ("Josh", "TxGEqnHWrfWFTfGW9XjX"),
            ("Adam", "pNInz6obpgDQGcFmaJgB"),
        ]
    
    def get_qwen_voices(self):
        """Returns Qwen TTS voice IDs."""
        return ["Cherry", "Stella", "Luna", "Bella", "Alice", "Nancy", "Cindy", "Emily"]


if __name__ == "__main__":
    pass
