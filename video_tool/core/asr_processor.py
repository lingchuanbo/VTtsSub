import os
import datetime

class ASRProcessor:
    def __init__(self, model_size="base", engine_type="whisper", api_key=None, api_url=None):
        """
        Initialize the ASR processor.
        
        Args:
            model_size (str): Whisper model size or Qwen model name
            engine_type (str): "whisper", "elevenlabs", or "qwen"
            api_key (str): API key (required for elevenlabs and qwen)
            api_url (str): API URL for Qwen (optional)
        """
        self.model_size = model_size
        self.engine_type = engine_type
        self.api_key = api_key
        self.api_url = api_url or "https://dashscope-intl.aliyuncs.com/api/v1"
        self.model = None
        # 断句参数
        self.pause_threshold = 0.5  # 停顿阈值（秒）
        self.max_words_per_segment = 12  # 每段最大词数

    def transcribe(self, audio_path, output_srt_path=None, language_code=None, diarize=False):
        """
        Transcribe audio file to text (SRT format).
        
        Args:
            audio_path (str): Path to the input audio file.
            output_srt_path (str): Path to save the SRT file. If None, returns the segments.
            language_code (str): Language code (e.g., "eng", "chi"). None for auto-detect.
            diarize (bool): Whether to annotate who is speaking (ElevenLabs only).
            
        Returns:
            list: List of segments if output_srt_path is None.
            str: Path to the saved SRT file if output_srt_path is provided.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if self.engine_type == "elevenlabs":
            segments = self._transcribe_elevenlabs(audio_path, language_code, diarize)
        elif self.engine_type == "qwen":
            segments = self._transcribe_qwen(audio_path, language_code)
        else:
            segments = self._transcribe_whisper(audio_path)
        
        if output_srt_path:
            self._save_as_srt(segments, output_srt_path)
            return output_srt_path
        
        return segments

    def _transcribe_whisper(self, audio_path):
        """Transcribe using Whisper in a separate process to avoid DLL conflicts."""
        import subprocess
        import json
        import sys
        
        # Get the path to the run_whisper.py script
        script_path = os.path.join(os.path.dirname(__file__), 'run_whisper.py')
        
        # Verify script exists
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Whisper script not found: {script_path}")
        
        # Model directory
        model_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models', 'whisper')
        os.makedirs(model_dir, exist_ok=True)
        
        # Check for bundled ffmpeg in the same directory as this script
        core_dir = os.path.dirname(__file__)
        ffmpeg_path = os.path.join(core_dir, 'ffmpeg.exe')
        
        # Prepare environment with ffmpeg in PATH
        env = os.environ.copy()
        if os.path.exists(ffmpeg_path):
            print(f"Found bundled ffmpeg: {ffmpeg_path}")
            # Add the core directory to PATH so ffmpeg.exe can be found
            env['PATH'] = core_dir + os.pathsep + env.get('PATH', '')
        else:
            print(f"Warning: ffmpeg.exe not found at {ffmpeg_path}")
            print("Whisper requires ffmpeg. Please install it or place ffmpeg.exe in video_tool/core/")
        
        print(f"Transcribing {audio_path} with Whisper (subprocess)...")
        print(f"Model: {self.model_size}")
        print(f"Script path: {script_path}")
        print(f"Python executable: {sys.executable}")
        
        # Build command
        cmd = [
            sys.executable,
            script_path,
            audio_path,
            "--model", self.model_size,
            "--model_dir", model_dir
        ]
        
        try:
            # Run subprocess with creationflags for Windows to avoid console window issues
            # Use startupinfo to hide console window on Windows
            startupinfo = None
            creationflags = 0
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                creationflags = subprocess.CREATE_NO_WINDOW
            
            # Run subprocess
            # Capture binary output to avoid UnicodeDecodeError in _readerthread
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=False,  # Return bytes
                check=False,
                startupinfo=startupinfo,
                creationflags=creationflags,
                env=env  # Pass modified environment with ffmpeg in PATH
            )
            
            # Helper to safely decode bytes
            def safe_decode(bytes_data):
                if not bytes_data:
                    return ""
                try:
                    return bytes_data.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        return bytes_data.decode('gbk')
                    except UnicodeDecodeError:
                        return bytes_data.decode('utf-8', errors='replace')

            stdout_str = safe_decode(process.stdout)
            stderr_str = safe_decode(process.stderr)
            
            if process.returncode != 0:
                print(f"Whisper subprocess error output: {stderr_str}")
                
                if "DLL" in stderr_str or "1114" in stderr_str:
                    raise RuntimeError(
                        f"Whisper 加载失败：PyTorch DLL 依赖问题\n\n"
                        f"解决方案：\n"
                        f"1. 推荐使用 ElevenLabs 或第三方 API（无需 PyTorch）\n"
                        f"2. 安装 Visual C++ Redistributable:\n"
                        f"   https://aka.ms/vs/17/release/vc_redist.x64.exe\n"
                        f"3. 重装 PyTorch CPU 版本:\n"
                        f"   pip install torch --index-url https://download.pytorch.org/whl/cpu\n\n"
                        f"详细错误: {stderr_str}"
                    )
                elif "WinError 2" in stderr_str or "找不到指定的文件" in stderr_str or "ffmpeg" in stderr_str.lower():
                    raise RuntimeError(
                        f"Whisper 无法找到 ffmpeg\n\n"
                        f"解决方案：\n"
                        f"1. 将 ffmpeg.exe 放到 video_tool/core/ 目录下\n"
                        f"2. 或安装 ffmpeg 并添加到系统 PATH\n"
                        f"   下载地址: https://www.gyan.dev/ffmpeg/builds/\n\n"
                        f"详细错误: {stderr_str}"
                    )
                else:
                    raise RuntimeError(f"Whisper subprocess failed: {stderr_str}")
            
            # Parse JSON output
            try:
                # stdout might contain other logs if not clean, try to find the JSON part
                # But run_whisper.py only prints JSON to stdout, unless libraries print to stdout
                # We'll try to parse the whole thing first
                result = json.loads(stdout_str)
                segments = result["segments"]
                # 基于词级时间戳优化字幕分段
                return self._optimize_segments_by_words(segments)
            except json.JSONDecodeError:
                # Try to find JSON object in the output (in case of noise)
                import re
                match = re.search(r'\{.*\}', stdout_str, re.DOTALL)
                if match:
                    try:
                        result = json.loads(match.group(0))
                        segments = result["segments"]
                        return self._optimize_segments_by_words(segments)
                    except:
                        pass
                raise RuntimeError(f"Failed to parse Whisper output: {stdout_str}")
                
        except Exception as e:
            raise RuntimeError(f"Error running Whisper subprocess: {str(e)}")

    def _transcribe_elevenlabs(self, audio_path, language_code=None, diarize=False):
        """Transcribe using ElevenLabs Speech-to-Text."""
        from elevenlabs.client import ElevenLabs
        
        if not self.api_key:
            raise ValueError("ElevenLabs API key is required")
        
        print(f"Transcribing {audio_path} with ElevenLabs...")
        client = ElevenLabs(api_key=self.api_key)
        
        with open(audio_path, "rb") as audio_file:
            transcription = client.speech_to_text.convert(
                file=audio_file,
                model_id="scribe_v1",
                tag_audio_events=True,
                language_code=language_code,
                diarize=diarize
            )
        
        # Convert ElevenLabs response to segments format
        segments = self._parse_elevenlabs_response(transcription)
        return segments

    def _parse_elevenlabs_response(self, transcription):
        """Parse ElevenLabs transcription response to segments format."""
        segments = []
        
        print(f"DEBUG: Transcription type: {type(transcription)}")
        print(f"DEBUG: Transcription attributes: {dir(transcription)}")
        
        # ElevenLabs API 返回的数据结构
        # 尝试访问不同的可能属性
        try:
            # 方法1: 检查是否有 words 属性（带时间戳的单词）
            if hasattr(transcription, 'words') and transcription.words:
                print(f"DEBUG: Found {len(transcription.words)} words")
                # 将单词组合成句子段落
                current_segment = {"start": 0, "end": 0, "text": "", "words": []}
                
                for word in transcription.words:
                    word_text = word.text if hasattr(word, 'text') else str(word)
                    word_start = word.start_time if hasattr(word, 'start_time') else (word.start if hasattr(word, 'start') else 0)
                    word_end = word.end_time if hasattr(word, 'end_time') else (word.end if hasattr(word, 'end') else 0)
                    
                    # 如果是新段落的开始或累积了足够的单词
                    if not current_segment["text"]:
                        current_segment["start"] = word_start
                    
                    current_segment["text"] += word_text + " "
                    current_segment["end"] = word_end
                    current_segment["words"].append(word_text)
                    
                    # 每10个单词或遇到句号创建一个新段落
                    if len(current_segment["words"]) >= 10 or word_text.strip().endswith(('.', '!', '?', '。', '！', '？')):
                        segments.append({
                            "start": current_segment["start"],
                            "end": current_segment["end"],
                            "text": current_segment["text"].strip()
                        })
                        current_segment = {"start": 0, "end": 0, "text": "", "words": []}
                
                # 添加最后一个段落
                if current_segment["text"]:
                    segments.append({
                        "start": current_segment["start"],
                        "end": current_segment["end"],
                        "text": current_segment["text"].strip()
                    })
            
            # 方法2: 检查是否有 segments 属性
            elif hasattr(transcription, 'segments') and transcription.segments:
                print(f"DEBUG: Found {len(transcription.segments)} segments")
                for segment in transcription.segments:
                    segments.append({
                        "start": getattr(segment, 'start_time', getattr(segment, 'start', 0)),
                        "end": getattr(segment, 'end_time', getattr(segment, 'end', 0)),
                        "text": getattr(segment, 'text', str(segment))
                    })
            
            # 方法3: 只有文本，没有时间戳
            elif hasattr(transcription, 'text'):
                print("DEBUG: Only text available, no timestamps")
                full_text = transcription.text
                # 按句子分割
                sentences = self._split_into_sentences(full_text)
                for i, sentence in enumerate(sentences):
                    segments.append({
                        "start": i * 5,  # 假设每句5秒
                        "end": (i + 1) * 5,
                        "text": sentence
                    })
            
            # 方法4: 完全回退
            else:
                print("DEBUG: Fallback to string conversion")
                text = str(transcription)
                sentences = self._split_into_sentences(text)
                for i, sentence in enumerate(sentences):
                    segments.append({
                        "start": i * 5,
                        "end": (i + 1) * 5,
                        "text": sentence
                    })
        
        except Exception as e:
            print(f"ERROR parsing ElevenLabs response: {e}")
            # 最终回退
            segments.append({
                "start": 0,
                "end": 0,
                "text": str(transcription)
            })
        
        print(f"DEBUG: Generated {len(segments)} segments")
        return segments
    
    def _transcribe_qwen(self, audio_path, language_code=None):
        """Transcribe using Qwen ASR API (third-party or DashScope)."""
        if not self.api_key:
            raise ValueError("Qwen API key is required")
        
        print(f"Transcribing {audio_path} with Qwen ASR...")
        
        # Check if using third-party API (contains /v1/audio/transcriptions)
        if '/v1/audio/transcriptions' in self.api_url or 'openai' in self.api_url.lower():
            print("Using third-party API (OpenAI-compatible)")
            segments = self._transcribe_qwen_third_party(audio_path, language_code)
        else:
            # Original DashScope implementation
            import dashscope
            from dashscope.audio.qwen_asr import QwenTranscription
            
            # Set API configuration
            dashscope.api_key = self.api_key
            dashscope.base_http_api_url = self.api_url
            
            # Check if audio_path is a URL or local file
            if audio_path.startswith('http://') or audio_path.startswith('https://'):
                print(f"Using provided URL: {audio_path}")
                segments = self._transcribe_qwen_with_url(audio_path, language_code)
            else:
                print("Warning: Using local file with DashScope may fail.")
                print("Starting local HTTP server for file access...")
                segments = self._transcribe_qwen_async(audio_path, language_code)
        
        return segments
    
    def _transcribe_qwen_third_party(self, audio_path, language_code=None):
        """Transcribe using third-party API (OpenAI-compatible)."""
        import requests
        
        print(f"Using third-party API: {self.api_url}")
        
        # Prepare the file
        if audio_path.startswith('http://') or audio_path.startswith('https://'):
            raise ValueError("Third-party API requires local file, not URL")
        
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        # Prepare request
        url = self.api_url
        if not url.endswith('/transcriptions'):
            if not url.endswith('/'):
                url += '/'
            url += 'v1/audio/transcriptions'
        
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        
        # Extract model name (remove description in parentheses)
        model_name = self.model_size.split(' ')[0] if ' ' in self.model_size else self.model_size
        
        # Prepare file upload
        with open(audio_path, 'rb') as audio_file:
            files = {
                'file': (os.path.basename(audio_path), audio_file, 'application/octet-stream')
            }
            
            # Prepare form data
            data = {
                'model': model_name,
                'response_format': 'verbose_json'  # Get timestamps
            }
            
            if language_code:
                data['language'] = language_code
            
            print(f"Uploading file to: {url}")
            print(f"Model: {model_name}")
            response = requests.post(url, headers=headers, data=data, files=files, timeout=300)
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code != 200:
            raise RuntimeError(f"API request failed ({response.status_code}): {response.text}")
        
        # Parse response
        result = response.json()
        print(f"Transcription result: {result.keys() if isinstance(result, dict) else type(result)}")
        
        # Convert to segments format
        segments = self._parse_third_party_response(result)
        return segments
    
    def _parse_third_party_response(self, result):
        """Parse third-party API response to segments format."""
        segments = []
        
        try:
            # OpenAI Whisper API format
            if 'segments' in result:
                for segment in result['segments']:
                    segments.append({
                        'start': segment.get('start', 0),
                        'end': segment.get('end', 0),
                        'text': segment.get('text', '')
                    })
            elif 'text' in result:
                # Only text, no timestamps
                text = result['text']
                sentences = self._split_into_sentences(text)
                for i, sentence in enumerate(sentences):
                    segments.append({
                        'start': i * 5,
                        'end': (i + 1) * 5,
                        'text': sentence
                    })
            else:
                # Unknown format
                segments.append({
                    'start': 0,
                    'end': 0,
                    'text': str(result)
                })
        except Exception as e:
            print(f"Error parsing response: {e}")
            segments.append({
                'start': 0,
                'end': 0,
                'text': str(result)
            })
        
        print(f"Generated {len(segments)} segments")
        return segments
    
    def _transcribe_qwen_with_url(self, file_url, language_code=None):
        """Transcribe using Qwen ASR with a direct URL."""
        import dashscope
        from dashscope.audio.qwen_asr import QwenTranscription
        
        try:
            print(f"Calling Qwen ASR with URL: {file_url}")
            
            # Start async transcription task
            task_response = QwenTranscription.async_call(
                model=self.model_size,
                file_url=file_url,
                language=language_code if language_code else "",
                enable_itn=False
            )
            
            print(f"Task response status: {task_response.status_code if task_response else 'None'}")
            
            if not task_response:
                raise RuntimeError(f"Qwen ASR 返回空响应。请检查 API Key 和网络连接。")
            
            if task_response.status_code != 200:
                error_msg = getattr(task_response, 'message', 'Unknown error')
                raise RuntimeError(f"Qwen ASR 调用失败 (状态码: {task_response.status_code}): {error_msg}")
            
            if not hasattr(task_response, 'output') or not hasattr(task_response.output, 'task_id'):
                raise RuntimeError(f"Qwen ASR 响应格式错误: {task_response}")
            
            task_id = task_response.output.task_id
            print(f"Task ID: {task_id}")
            
            # Wait for task completion
            print("Waiting for transcription to complete...")
            task_result = QwenTranscription.wait(task=task_id)
            
            print(f"Transcription completed with status: {task_result.status_code}")
            
            if task_result.status_code != 200:
                error_msg = getattr(task_result, 'message', 'Unknown error')
                raise RuntimeError(f"转录失败: {error_msg}")
            
            # Parse result
            segments = self._parse_qwen_response(task_result)
            return segments
            
        except Exception as e:
            print(f"Error: {type(e).__name__}: {str(e)}")
            raise
    
    def _transcribe_qwen_async(self, audio_path, language_code=None):
        """Use async method with local HTTP server."""
        import dashscope
        from dashscope.audio.qwen_asr import QwenTranscription
        import threading
        from http.server import HTTPServer, SimpleHTTPRequestHandler
        import socket
        import time
        from urllib.parse import quote
        
        # Find available port
        def find_free_port():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', 0))
                s.listen(1)
                port = s.getsockname()[1]
            return port
        
        port = find_free_port()
        
        # Get file directory and name
        file_dir = os.path.dirname(os.path.abspath(audio_path))
        file_name = os.path.basename(audio_path)
        
        # Start local HTTP server
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=file_dir, **kwargs)
            
            def log_message(self, format, *args):
                print(f"HTTP Server: {format % args}")
        
        server = HTTPServer(('0.0.0.0', port), Handler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        
        # Wait for server to start
        time.sleep(0.5)
        
        try:
            # URL encode the filename to handle spaces and special characters
            encoded_filename = quote(file_name)
            file_url = f"http://127.0.0.1:{port}/{encoded_filename}"
            print(f"Serving file at: {file_url}")
            
            # Test if file is accessible
            import urllib.request
            try:
                with urllib.request.urlopen(file_url, timeout=5) as response:
                    file_size = len(response.read())
                    print(f"File accessible, size: {file_size} bytes")
            except Exception as e:
                print(f"Warning: Could not verify file access: {e}")
                # Try without encoding
                file_url_alt = f"http://127.0.0.1:{port}/{file_name}"
                print(f"Trying alternative URL: {file_url_alt}")
            
            # Start async transcription task
            print(f"Calling Qwen ASR with model: {self.model_size}")
            task_response = QwenTranscription.async_call(
                model=self.model_size,
                file_url=file_url,
                language=language_code if language_code else "",
                enable_itn=False
            )
            
            print(f"Task response: {task_response}")
            print(f"Response status: {task_response.status_code if task_response else 'None'}")
            
            if not task_response:
                raise RuntimeError(f"Qwen ASR 返回空响应。请检查 API Key 和网络连接。")
            
            if task_response.status_code == 404:
                raise RuntimeError(
                    f"Qwen ASR 无法访问文件 (404)。\n\n"
                    f"原因：Qwen ASR 是云端服务，无法访问本地文件。\n\n"
                    f"解决方案：\n"
                    f"1. 推荐使用 Whisper（本地运行，无需上传）\n"
                    f"2. 或使用 ElevenLabs（支持直接上传文件）\n"
                    f"3. 或将文件上传到阿里云 OSS，然后使用公网 URL\n\n"
                    f"Qwen ASR 适合已有公网可访问音频 URL 的场景。"
                )
            
            if task_response.status_code != 200:
                error_msg = getattr(task_response, 'message', 'Unknown error')
                raise RuntimeError(f"Qwen ASR 调用失败 (状态码: {task_response.status_code}): {error_msg}")
            
            if not hasattr(task_response, 'output') or not hasattr(task_response.output, 'task_id'):
                raise RuntimeError(f"Qwen ASR 响应格式错误: {task_response}")
            
            task_id = task_response.output.task_id
            print(f"Task ID: {task_id}")
            
            # Wait for task completion
            print("Waiting for transcription to complete...")
            task_result = QwenTranscription.wait(task=task_id)
            
            print(f"Transcription completed with status: {task_result.status_code}")
            
            if task_result.status_code != 200:
                error_msg = getattr(task_result, 'message', 'Unknown error')
                raise RuntimeError(f"转录失败: {error_msg}")
            
            # Parse result
            segments = self._parse_qwen_response(task_result)
            return segments
            
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            print(f"Detailed error: {error_type}: {error_msg}")
            
            # Provide user-friendly error message
            if "Connection" in error_type or "404" in error_msg:
                raise RuntimeError(
                    f"Qwen ASR 无法访问本地文件。\n\n"
                    f"原因：Qwen ASR 是云端服务，无法访问 localhost。\n\n"
                    f"解决方案：\n"
                    f"1. 将音频上传到阿里云 OSS 或其他云存储\n"
                    f"2. 在 '或 URL' 输入框中输入公网可访问的 URL\n"
                    f"3. 或改用 Whisper（本地）或 ElevenLabs（支持上传）\n\n"
                    f"技术细节: {error_type}: {error_msg}"
                )
            else:
                raise
            
        finally:
            # Stop server
            print("Shutting down HTTP server...")
            server.shutdown()
    
    def _parse_qwen_response(self, task_result):
        """Parse Qwen ASR response to segments format."""
        segments = []
        
        print(f"DEBUG: Qwen result status: {task_result.status_code}")
        print(f"DEBUG: Qwen result output: {task_result.output}")
        
        try:
            # Qwen ASR returns transcription with timestamps
            if hasattr(task_result.output, 'results'):
                results = task_result.output.results
                
                for result in results:
                    # Extract text and timestamps
                    if hasattr(result, 'transcription_result'):
                        trans_result = result.transcription_result
                        
                        # Check for sentences with timestamps
                        if hasattr(trans_result, 'sentences'):
                            for sentence in trans_result.sentences:
                                segments.append({
                                    "start": sentence.begin_time / 1000.0 if hasattr(sentence, 'begin_time') else 0,
                                    "end": sentence.end_time / 1000.0 if hasattr(sentence, 'end_time') else 0,
                                    "text": sentence.text if hasattr(sentence, 'text') else str(sentence)
                                })
                        # Fallback to full text
                        elif hasattr(trans_result, 'text'):
                            text = trans_result.text
                            sentences = self._split_into_sentences(text)
                            for i, sentence in enumerate(sentences):
                                segments.append({
                                    "start": i * 5,
                                    "end": (i + 1) * 5,
                                    "text": sentence
                                })
            
            # Fallback: try to get text directly
            elif hasattr(task_result.output, 'text'):
                text = task_result.output.text
                sentences = self._split_into_sentences(text)
                for i, sentence in enumerate(sentences):
                    segments.append({
                        "start": i * 5,
                        "end": (i + 1) * 5,
                        "text": sentence
                    })
            
            # Last resort
            else:
                text = str(task_result.output)
                segments.append({
                    "start": 0,
                    "end": 0,
                    "text": text
                })
        
        except Exception as e:
            print(f"ERROR parsing Qwen response: {e}")
            segments.append({
                "start": 0,
                "end": 0,
                "text": str(task_result.output)
            })
        
        print(f"DEBUG: Generated {len(segments)} segments from Qwen")
        return segments
    
    def _split_into_sentences(self, text):
        """将文本分割成句子"""
        import re
        # 按句号、问号、感叹号分割
        sentences = re.split(r'([.!?。！？]+)', text)
        result = []
        for i in range(0, len(sentences)-1, 2):
            sentence = (sentences[i] + (sentences[i+1] if i+1 < len(sentences) else '')).strip()
            if sentence:
                result.append(sentence)
        # 处理最后一个句子（如果没有标点）
        if len(sentences) % 2 == 1 and sentences[-1].strip():
            result.append(sentences[-1].strip())
        return result if result else [text]
    
    def _optimize_segments_by_words(self, segments, pause_threshold=None, max_words_per_segment=None):
        """
        基于词级时间戳优化字幕分段，让字幕与语音精确同步
        
        Args:
            segments: Whisper 返回的原始 segments
            pause_threshold: 停顿阈值（秒），超过此时间视为新段落
            max_words_per_segment: 每段最大词数
            
        Returns:
            优化后的 segments 列表
        """
        # 使用实例属性或默认值
        if pause_threshold is None:
            pause_threshold = getattr(self, 'pause_threshold', 0.5)
        if max_words_per_segment is None:
            max_words_per_segment = getattr(self, 'max_words_per_segment', 12)
        
        optimized = []
        
        for segment in segments:
            # 检查是否有词级时间戳
            words = segment.get("words", [])
            
            if not words:
                # 没有词级时间戳，保持原样
                optimized.append({
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": segment["text"]
                })
                continue
            
            # 基于停顿和词数重新分段
            current_segment = {
                "start": None,
                "end": None,
                "words": []
            }
            
            for i, word_info in enumerate(words):
                word = word_info.get("word", "")
                word_start = word_info.get("start", 0)
                word_end = word_info.get("end", 0)
                
                # 检查是否需要开始新段落（在添加当前词之前）
                start_new_segment = False
                
                if current_segment["start"] is None:
                    # 第一个词，不分段
                    start_new_segment = False
                elif len(current_segment["words"]) >= max_words_per_segment:
                    # 达到最大词数，强制分段
                    start_new_segment = True
                elif word_start - current_segment["end"] > pause_threshold:
                    # 停顿超过阈值，分段
                    start_new_segment = True
                
                if start_new_segment and current_segment["words"]:
                    # 保存当前段落
                    optimized.append({
                        "start": current_segment["start"],
                        "end": current_segment["end"],
                        "text": "".join(current_segment["words"]).strip()
                    })
                    current_segment = {
                        "start": None,
                        "end": None,
                        "words": []
                    }
                
                # 添加当前词
                if current_segment["start"] is None:
                    current_segment["start"] = word_start
                current_segment["end"] = word_end
                current_segment["words"].append(word)
            
            # 保存最后一个段落
            if current_segment["words"]:
                optimized.append({
                    "start": current_segment["start"],
                    "end": current_segment["end"],
                    "text": "".join(current_segment["words"]).strip()
                })
        
        return optimized

    def optimize_with_ai(self, segments, api_key, api_url, model, optimize_level="medium", progress_callback=None):
        """
        使用 AI 优化字幕的断句和流畅度
        
        Args:
            segments: 字幕段落列表 [{"start": float, "end": float, "text": str}, ...]
            api_key: API Key
            api_url: API URL
            model: 模型名称
            optimize_level: 优化强度 "light"(轻度), "medium"(中度), "heavy"(重度)
            progress_callback: 进度回调函数
            
        Returns:
            优化后的 segments 列表
        """
        import requests
        import re
        
        if not segments:
            return segments
        
        # 根据优化强度选择提示词
        if optimize_level == "light":
            system_prompt = """你是字幕断句专家。请优化以下ASR识别的字幕断句，使其更自然。

规则：
1. 只调整断句位置，不修改文字内容
2. 在语义完整的地方断句，避免句子中间断开
3. 可以合并过短的相邻句子，或拆分过长的句子
4. 保持时间轴连续，合理分配时间"""
        elif optimize_level == "heavy":
            system_prompt = """你是专业字幕编辑。请完全重写以下ASR识别的字幕，使其流畅自然。

规则：
1. 可以完全重写句子，使表达更清晰流畅
2. 删除所有口语化的填充词和重复
3. 优化断句，使每条字幕长度适中
4. 保持原意不变，时间轴合理分配"""
        else:  # medium
            system_prompt = """你是字幕优化专家。请优化以下ASR识别的字幕，使其更流畅。

规则：
1. 优化断句位置，在语义完整处断开
2. 适当润色语句，删除明显的口语填充词（如"嗯"、"那个"）
3. 保持原意和风格不变
4. 时间轴需要合理对应文本长度"""
        
        # 准备输入数据
        input_lines = []
        for i, seg in enumerate(segments):
            start_ts = self._format_timestamp(seg["start"])
            end_ts = self._format_timestamp(seg["end"])
            input_lines.append(f"{i+1}|{start_ts}|{end_ts}|{seg['text']}")
        
        # 分批处理（每批20条）
        batch_size = 20
        all_optimized = []
        total_batches = (len(input_lines) + batch_size - 1) // batch_size
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, len(input_lines))
            batch_lines = input_lines[start_idx:end_idx]
            
            if progress_callback:
                progress_callback(f"AI优化中... 批次 {batch_idx + 1}/{total_batches}")
            
            user_message = f"""请优化以下 {len(batch_lines)} 条字幕：

{chr(10).join(batch_lines)}

输出格式要求：
- 每行格式: 序号|开始时间|结束时间|优化后文本
- 时间格式: HH:MM:SS,mmm
- 可以合并或拆分条目，但时间必须连续
- 只输出优化结果，不要其他说明"""
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.3
            }
            
            try:
                response = requests.post(api_url, headers=headers, json=payload, timeout=120)
                
                if response.status_code != 200:
                    print(f"AI优化请求失败 ({response.status_code}): {response.text}")
                    # 失败时保留原始数据
                    for line in batch_lines:
                        parts = line.split('|', 3)
                        if len(parts) == 4:
                            all_optimized.append({
                                "start": self._parse_timestamp(parts[1]),
                                "end": self._parse_timestamp(parts[2]),
                                "text": parts[3]
                            })
                    continue
                
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                # 解析优化结果
                optimized_batch = self._parse_ai_optimized_response(content, batch_lines)
                all_optimized.extend(optimized_batch)
                
            except Exception as e:
                print(f"AI优化出错: {e}")
                # 失败时保留原始数据
                for line in batch_lines:
                    parts = line.split('|', 3)
                    if len(parts) == 4:
                        all_optimized.append({
                            "start": self._parse_timestamp(parts[1]),
                            "end": self._parse_timestamp(parts[2]),
                            "text": parts[3]
                        })
        
        if progress_callback:
            progress_callback(f"AI优化完成，共 {len(all_optimized)} 条字幕")
        
        return all_optimized if all_optimized else segments
    
    def _parse_ai_optimized_response(self, content, original_lines):
        """解析AI优化后的响应"""
        import re
        
        optimized = []
        lines = content.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('```'):
                continue
            
            # 匹配格式: 序号|时间|时间|文本
            match = re.match(r'^(\d+)\|([^|]+)\|([^|]+)\|(.+)$', line)
            if match:
                try:
                    start_time = self._parse_timestamp(match.group(2).strip())
                    end_time = self._parse_timestamp(match.group(3).strip())
                    text = match.group(4).strip()
                    
                    if text and end_time > start_time:
                        optimized.append({
                            "start": start_time,
                            "end": end_time,
                            "text": text
                        })
                except Exception as e:
                    print(f"解析行失败: {line}, 错误: {e}")
                    continue
        
        # 如果解析失败，返回原始数据
        if not optimized:
            print("AI响应解析失败，使用原始字幕")
            for line in original_lines:
                parts = line.split('|', 3)
                if len(parts) == 4:
                    optimized.append({
                        "start": self._parse_timestamp(parts[1]),
                        "end": self._parse_timestamp(parts[2]),
                        "text": parts[3]
                    })
        
        return optimized
    
    def _parse_timestamp(self, ts_str):
        """解析 SRT 时间戳为秒数"""
        import re
        
        ts_str = ts_str.strip()
        # 匹配 HH:MM:SS,mmm 或 HH:MM:SS.mmm
        match = re.match(r'(\d+):(\d+):(\d+)[,.](\d+)', ts_str)
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            millis = int(match.group(4))
            return hours * 3600 + minutes * 60 + seconds + millis / 1000.0
        
        # 尝试简单格式 MM:SS,mmm
        match = re.match(r'(\d+):(\d+)[,.](\d+)', ts_str)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            millis = int(match.group(3))
            return minutes * 60 + seconds + millis / 1000.0
        
        return 0.0

    def _save_as_srt(self, segments, output_path):
        """
        Save transcription segments to an SRT file.
        """
        with open(output_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments):
                start = self._format_timestamp(segment["start"])
                end = self._format_timestamp(segment["end"])
                text = segment["text"].strip()
                
                f.write(f"{i + 1}\n")
                f.write(f"{start} --> {end}\n")
                f.write(f"{text}\n\n")
        print(f"SRT saved to {output_path}")

    def _format_timestamp(self, seconds):
        """
        Format seconds to SRT timestamp format (HH:MM:SS,mmm).
        """
        td = datetime.timedelta(seconds=seconds)
        # Handle milliseconds
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        millis = int((td.total_seconds() - total_seconds) * 1000)
        
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

if __name__ == "__main__":
    # Test
    # processor = ASRProcessor()
    # processor.transcribe("test.mp3", "test.srt")
    pass
