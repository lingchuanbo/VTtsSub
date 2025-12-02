"""
ASR2TTS 全流程管道

完整流程：
1. ASR 带时间戳（Whisper + Silero-VAD）
2. 智能合并与句子重组
3. 上下文感知翻译
4. 时间戳重对齐（为 TTS 准备）
5. TTS 生成（可选）

使用示例：
    pipeline = ASR2TTSPipeline()
    pipeline.configure_asr(model_size="base", use_vad=True)
    pipeline.configure_translator(api_key="xxx", api_url="xxx")
    
    result = pipeline.process("audio.mp3", target_lang="zh")
    # result 包含对齐后的字幕和 TTS 数据
"""

import os
import json
from typing import Optional, List, Dict, Any, Callable


class ASR2TTSPipeline:
    """ASR 到 TTS 的完整处理管道"""
    
    def __init__(self):
        """初始化管道"""
        self.asr_processor = None
        self.subtitle_manager = None
        self.tts_engine = None
        
        # 配置参数
        self.asr_config = {
            "model_size": "base",
            "use_vad": True,
            "vad_threshold": 0.5,
            "pause_threshold": 0.5,
            "max_words_per_segment": 12
        }
        
        self.translator_config = {
            "engine_type": "deepseek",
            "api_key": None,
            "api_url": "https://api.deepseek.com/v1/chat/completions",
            "model": "deepseek-chat",
            "thread_count": 3,
            "request_interval": 2.0
        }
        
        self.tts_config = {
            "engine": "f5-tts",
            "speaker_rate": 1.0
        }
    
    def configure_asr(self, model_size: str = "base", use_vad: bool = True,
                      vad_threshold: float = 0.5, pause_threshold: float = 0.5,
                      max_words_per_segment: int = 12):
        """
        配置 ASR 参数
        
        Args:
            model_size: Whisper 模型大小 (tiny/base/small/medium/large)
            use_vad: 是否启用 Silero-VAD
            vad_threshold: VAD 阈值 (0.1-0.9)
            pause_threshold: 停顿阈值（秒）
            max_words_per_segment: 每段最大词数
        """
        self.asr_config.update({
            "model_size": model_size,
            "use_vad": use_vad,
            "vad_threshold": vad_threshold,
            "pause_threshold": pause_threshold,
            "max_words_per_segment": max_words_per_segment
        })
    
    def configure_translator(self, api_key: str, api_url: str = None,
                             model: str = None, engine_type: str = "deepseek",
                             thread_count: int = 3, request_interval: float = 2.0):
        """
        配置翻译器参数
        
        Args:
            api_key: API 密钥
            api_url: API 地址
            model: 模型名称
            engine_type: 引擎类型 (deepseek/openrouter/custom)
            thread_count: 并发数
            request_interval: 请求间隔（秒）
        """
        self.translator_config.update({
            "api_key": api_key,
            "engine_type": engine_type,
            "thread_count": thread_count,
            "request_interval": request_interval
        })
        if api_url:
            self.translator_config["api_url"] = api_url
        if model:
            self.translator_config["model"] = model
    
    def configure_tts(self, engine: str = "f5-tts", speaker_rate: float = 1.0):
        """
        配置 TTS 参数
        
        Args:
            engine: TTS 引擎
            speaker_rate: 语速倍率
        """
        self.tts_config.update({
            "engine": engine,
            "speaker_rate": speaker_rate
        })
    
    def _init_asr(self):
        """初始化 ASR 处理器"""
        if self.asr_processor is None:
            from video_tool.core.asr_processor import ASRProcessor
            self.asr_processor = ASRProcessor(
                model_size=self.asr_config["model_size"],
                engine_type="whisper"
            )
            self.asr_processor.pause_threshold = self.asr_config["pause_threshold"]
            self.asr_processor.max_words_per_segment = self.asr_config["max_words_per_segment"]
            self.asr_processor.use_vad = self.asr_config["use_vad"]
            self.asr_processor.vad_threshold = self.asr_config["vad_threshold"]
    
    def _init_translator(self):
        """初始化翻译器"""
        if self.subtitle_manager is None:
            from video_tool.core.subtitle_manager import SubtitleManager
            self.subtitle_manager = SubtitleManager()
        
        self.subtitle_manager.set_engine(
            self.translator_config["engine_type"],
            self.translator_config["api_key"],
            self.translator_config["api_url"],
            self.translator_config["model"]
        )
        self.subtitle_manager.set_thread_count(self.translator_config["thread_count"])
        self.subtitle_manager.set_request_interval(self.translator_config["request_interval"])
    
    def _init_tts(self):
        """初始化 TTS 引擎"""
        if self.tts_engine is None:
            try:
                from video_tool.core.tts_engine import TTSEngine
                self.tts_engine = TTSEngine()
            except ImportError:
                print("警告: TTS 引擎未安装")
                self.tts_engine = None

    
    def process(self, audio_path: str, target_lang: str = "zh",
                output_dir: str = None, progress_callback: Callable = None,
                skip_tts: bool = False) -> Dict[str, Any]:
        """
        执行完整的 ASR → 翻译 → TTS 流程
        
        Args:
            audio_path: 输入音频文件路径
            target_lang: 目标语言 (zh/ja/ko/en)
            output_dir: 输出目录（默认与输入文件同目录）
            progress_callback: 进度回调函数 (stage, progress, message)
            skip_tts: 是否跳过 TTS 生成
            
        Returns:
            dict: {
                "segments": 原始 ASR 段落,
                "translated": 翻译后的字幕,
                "aligned": 对齐后的数据,
                "tts_audio": TTS 音频路径（如果生成）,
                "output_files": 输出文件列表
            }
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        # 设置输出目录
        if output_dir is None:
            output_dir = os.path.dirname(audio_path)
        os.makedirs(output_dir, exist_ok=True)
        
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        
        result = {
            "segments": [],
            "translated": [],
            "aligned": [],
            "tts_audio": None,
            "output_files": []
        }
        
        def emit_progress(stage, progress, message):
            if progress_callback:
                progress_callback(stage, progress, message)
            print(f"[{stage}] {progress}% - {message}")
        
        # ========== 阶段 1: ASR 带时间戳 ==========
        emit_progress("ASR", 0, "初始化 ASR 处理器...")
        self._init_asr()
        
        emit_progress("ASR", 10, f"开始语音识别 (模型: {self.asr_config['model_size']})...")
        segments = self.asr_processor.transcribe(audio_path)
        
        emit_progress("ASR", 100, f"ASR 完成，识别到 {len(segments)} 个段落")
        result["segments"] = segments
        
        # 保存原始 ASR 结果
        asr_srt_path = os.path.join(output_dir, f"{base_name}.asr.srt")
        self.asr_processor._save_as_srt(segments, asr_srt_path)
        result["output_files"].append(asr_srt_path)
        
        # ========== 阶段 2: 转换为字幕格式 ==========
        emit_progress("转换", 0, "转换为字幕格式...")
        subtitles = self._segments_to_subtitles(segments)
        
        # ========== 阶段 3: 上下文感知翻译 ==========
        if not self.translator_config.get("api_key"):
            emit_progress("翻译", 0, "跳过翻译（未配置 API）")
            translated_subs = subtitles
        else:
            emit_progress("翻译", 0, "初始化翻译器...")
            self._init_translator()
            
            emit_progress("翻译", 10, f"开始翻译到 {target_lang}...")
            
            def translate_progress(current, total):
                pct = int(10 + (current / total) * 80)
                emit_progress("翻译", pct, f"翻译进度: {current}/{total}")
            
            translated_subs = self.subtitle_manager.translate_subtitles(
                subtitles, target_lang, progress_callback=translate_progress
            )
            
            emit_progress("翻译", 100, "翻译完成")
        
        result["translated"] = translated_subs
        
        # 保存翻译结果
        lang_suffix = {"zh": "chs", "ja": "jpn", "ko": "kor", "en": "eng"}.get(target_lang, target_lang)
        trans_srt_path = os.path.join(output_dir, f"{base_name}.{lang_suffix}.srt")
        self.subtitle_manager.save_srt(translated_subs, trans_srt_path)
        result["output_files"].append(trans_srt_path)
        
        # ========== 阶段 4: 时间戳重对齐 ==========
        emit_progress("对齐", 0, "时间戳对齐...")
        
        translated_texts = [sub['text'] for sub in translated_subs]
        aligned = self.subtitle_manager.align_translation_timestamps(
            subtitles, translated_texts, target_lang,
            speaker_rate=self.tts_config.get("speaker_rate", 1.0)
        )
        
        result["aligned"] = aligned
        emit_progress("对齐", 100, "时间戳对齐完成")
        
        # 导出 TTS 对齐数据
        tts_json_path = os.path.join(output_dir, f"{base_name}.tts_alignment.json")
        self.subtitle_manager.export_tts_alignment_data(aligned, tts_json_path)
        result["output_files"].append(tts_json_path)
        
        # ========== 阶段 5: TTS 生成（可选）==========
        if not skip_tts and self.tts_engine is not None:
            emit_progress("TTS", 0, "初始化 TTS 引擎...")
            self._init_tts()
            
            emit_progress("TTS", 10, "生成语音...")
            tts_audio_path = os.path.join(output_dir, f"{base_name}.{lang_suffix}.wav")
            
            # TTS 生成逻辑（根据实际 TTS 引擎实现）
            try:
                self._generate_tts(aligned, tts_audio_path, target_lang)
                result["tts_audio"] = tts_audio_path
                result["output_files"].append(tts_audio_path)
                emit_progress("TTS", 100, "TTS 生成完成")
            except Exception as e:
                emit_progress("TTS", 100, f"TTS 生成失败: {e}")
        else:
            emit_progress("TTS", 100, "跳过 TTS 生成")
        
        # ========== 完成 ==========
        emit_progress("完成", 100, f"全流程完成，输出 {len(result['output_files'])} 个文件")
        
        return result
    
    def _segments_to_subtitles(self, segments: List[Dict]) -> List[Dict]:
        """
        将 ASR segments 转换为字幕格式
        """
        subtitles = []
        for i, seg in enumerate(segments):
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            text = seg.get("text", "").strip()
            
            if not text:
                continue
            
            # 格式化时间戳
            start_ts = self._format_timestamp(start)
            end_ts = self._format_timestamp(end)
            
            subtitles.append({
                "index": str(i + 1),
                "time_range": f"{start_ts} --> {end_ts}",
                "text": text
            })
        
        return subtitles
    
    def _format_timestamp(self, seconds: float) -> str:
        """格式化时间戳为 SRT 格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    def _generate_tts(self, aligned_segments: List[Dict], output_path: str, 
                      target_lang: str):
        """
        生成 TTS 音频
        
        Args:
            aligned_segments: 对齐后的字幕段落
            output_path: 输出音频路径
            target_lang: 目标语言
        """
        if self.tts_engine is None:
            raise RuntimeError("TTS 引擎未初始化")
        
        # 合并所有文本
        texts = [seg['text'] for seg in aligned_segments]
        
        # 调用 TTS 引擎（根据实际实现调整）
        # self.tts_engine.synthesize(texts, output_path, language=target_lang)
        
        # 占位实现
        print(f"TTS 生成: {len(texts)} 段文本 -> {output_path}")
    
    def process_srt(self, srt_path: str, target_lang: str = "zh",
                    output_dir: str = None, progress_callback: Callable = None) -> Dict[str, Any]:
        """
        处理已有的 SRT 文件（跳过 ASR 阶段）
        
        Args:
            srt_path: 输入 SRT 文件路径
            target_lang: 目标语言
            output_dir: 输出目录
            progress_callback: 进度回调
            
        Returns:
            处理结果
        """
        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"SRT 文件不存在: {srt_path}")
        
        # 设置输出目录
        if output_dir is None:
            output_dir = os.path.dirname(srt_path)
        
        base_name = os.path.splitext(os.path.basename(srt_path))[0]
        
        result = {
            "segments": [],
            "translated": [],
            "aligned": [],
            "output_files": []
        }
        
        def emit_progress(stage, progress, message):
            if progress_callback:
                progress_callback(stage, progress, message)
            print(f"[{stage}] {progress}% - {message}")
        
        # 初始化翻译器
        self._init_translator()
        
        # 加载 SRT
        emit_progress("加载", 0, "加载 SRT 文件...")
        subtitles = self.subtitle_manager.parse_srt(srt_path)
        result["segments"] = subtitles
        emit_progress("加载", 100, f"加载完成，共 {len(subtitles)} 条字幕")
        
        # 翻译
        if self.translator_config.get("api_key"):
            emit_progress("翻译", 0, "开始翻译...")
            
            def translate_progress(current, total):
                pct = int((current / total) * 90)
                emit_progress("翻译", pct, f"翻译进度: {current}/{total}")
            
            translated_subs = self.subtitle_manager.translate_subtitles(
                subtitles, target_lang, progress_callback=translate_progress
            )
            result["translated"] = translated_subs
            emit_progress("翻译", 100, "翻译完成")
            
            # 保存翻译结果
            lang_suffix = {"zh": "chs", "ja": "jpn", "ko": "kor"}.get(target_lang, target_lang)
            trans_path = os.path.join(output_dir, f"{base_name}.{lang_suffix}.srt")
            self.subtitle_manager.save_srt(translated_subs, trans_path)
            result["output_files"].append(trans_path)
            
            # 时间戳对齐
            emit_progress("对齐", 0, "时间戳对齐...")
            translated_texts = [sub['text'] for sub in translated_subs]
            aligned = self.subtitle_manager.align_translation_timestamps(
                subtitles, translated_texts, target_lang
            )
            result["aligned"] = aligned
            
            # 导出对齐数据
            tts_json_path = os.path.join(output_dir, f"{base_name}.tts_alignment.json")
            self.subtitle_manager.export_tts_alignment_data(aligned, tts_json_path)
            result["output_files"].append(tts_json_path)
            emit_progress("对齐", 100, "对齐完成")
        
        emit_progress("完成", 100, "处理完成")
        return result


# 便捷函数
def create_pipeline(asr_model: str = "base", api_key: str = None, 
                    api_url: str = None) -> ASR2TTSPipeline:
    """
    创建并配置管道的便捷函数
    
    Args:
        asr_model: Whisper 模型大小
        api_key: 翻译 API 密钥
        api_url: 翻译 API 地址
        
    Returns:
        配置好的 ASR2TTSPipeline 实例
    """
    pipeline = ASR2TTSPipeline()
    pipeline.configure_asr(model_size=asr_model, use_vad=True)
    
    if api_key:
        pipeline.configure_translator(api_key=api_key, api_url=api_url)
    
    return pipeline


if __name__ == "__main__":
    # 测试示例
    print("ASR2TTS Pipeline 模块")
    print("=" * 50)
    print("""
使用示例:

    from video_tool.core.asr2tts_pipeline import ASR2TTSPipeline
    
    # 创建管道
    pipeline = ASR2TTSPipeline()
    
    # 配置 ASR
    pipeline.configure_asr(
        model_size="base",
        use_vad=True,
        vad_threshold=0.5
    )
    
    # 配置翻译器
    pipeline.configure_translator(
        api_key="your-api-key",
        api_url="https://api.deepseek.com/v1/chat/completions",
        model="deepseek-chat"
    )
    
    # 执行完整流程
    result = pipeline.process(
        "input_audio.mp3",
        target_lang="zh",
        output_dir="./output"
    )
    
    print(f"输出文件: {result['output_files']}")
    """)
