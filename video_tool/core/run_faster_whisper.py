"""
Faster-Whisper ASR 处理器

使用 faster-whisper + silero-vad 组合，提供：
1. 更快的推理速度（CTranslate2 优化）
2. 内置 VAD 过滤
3. 流式处理支持
4. 更低的显存占用

安装：
    pip install faster-whisper

使用：
    python run_faster_whisper.py audio.wav --model large-v2 --device cuda
"""

import argparse
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")


def evaluate_asr_quality(segments: list) -> dict:
    """
    评估 ASR 质量
    
    Args:
        segments: 转录段落列表
        
    Returns:
        质量指标字典
    """
    if not segments:
        return {
            "total_segments": 0,
            "avg_words_per_segment": 0,
            "segments_with_punctuation": 0,
            "punctuation_ratio": 0,
            "avg_duration": 0,
            "avg_confidence": 0,
            "short_segments": 0,
            "long_segments": 0,
            "quality_score": 0
        }
    
    total = len(segments)
    
    # 计算各项指标
    word_counts = []
    durations = []
    confidences = []
    punctuation_count = 0
    short_count = 0  # < 1秒
    long_count = 0   # > 10秒
    
    for seg in segments:
        text = seg.get("text", "").strip()
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        
        # 词数
        words = len(text.split())
        word_counts.append(words)
        
        # 时长
        duration = end - start
        durations.append(duration)
        
        if duration < 1:
            short_count += 1
        elif duration > 10:
            long_count += 1
        
        # 标点
        if text and text[-1] in '.!?。！？':
            punctuation_count += 1
        
        # 置信度（如果有）
        if "confidence" in seg:
            confidences.append(seg["confidence"])
    
    avg_words = sum(word_counts) / total
    avg_duration = sum(durations) / total
    punctuation_ratio = punctuation_count / total
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0
    
    # 计算质量得分 (0-1)
    # 理想值：平均 8-15 词/段，2-6 秒/段，高标点率
    word_score = 1 - abs(avg_words - 10) / 10  # 10词最佳
    duration_score = 1 - abs(avg_duration - 4) / 4  # 4秒最佳
    punctuation_score = punctuation_ratio
    segment_balance_score = 1 - (short_count + long_count) / total
    
    quality_score = (
        max(0, word_score) * 0.25 +
        max(0, duration_score) * 0.25 +
        punctuation_score * 0.25 +
        max(0, segment_balance_score) * 0.25
    )
    
    return {
        "total_segments": total,
        "avg_words_per_segment": round(avg_words, 2),
        "segments_with_punctuation": punctuation_count,
        "punctuation_ratio": round(punctuation_ratio, 3),
        "avg_duration": round(avg_duration, 2),
        "avg_confidence": round(avg_confidence, 3),
        "short_segments": short_count,
        "long_segments": long_count,
        "quality_score": round(quality_score, 3)
    }


def transcribe_with_faster_whisper(
    audio_path: str,
    model_size: str = "base",
    device: str = "auto",
    compute_type: str = "auto",
    language: str = None,
    use_vad: bool = True,
    vad_min_silence_ms: int = 500,
    vad_speech_pad_ms: int = 400,
    word_timestamps: bool = True,
    condition_on_previous: bool = True,
    initial_prompt: str = None,
    temperature: float = 0.0,
    beam_size: int = 5,
    best_of: int = 5
) -> dict:
    """
    使用 faster-whisper 进行转录
    
    Args:
        audio_path: 音频文件路径
        model_size: 模型大小 (tiny/base/small/medium/large-v2/large-v3)
        device: 设备 (auto/cuda/cpu)
        compute_type: 计算类型 (auto/float16/int8/int8_float16)
        language: 语言代码（None 为自动检测）
        use_vad: 是否使用 VAD 过滤
        vad_min_silence_ms: VAD 最小静音时长（毫秒）
        vad_speech_pad_ms: VAD 语音填充（毫秒）
        word_timestamps: 是否生成词级时间戳
        condition_on_previous: 是否基于上文条件
        initial_prompt: 初始提示词
        temperature: 采样温度
        beam_size: Beam search 大小
        best_of: 采样数量
        
    Returns:
        {
            "segments": [...],
            "text": str,
            "language": str,
            "quality_metrics": {...}
        }
    """
    from faster_whisper import WhisperModel
    
    # 自动选择设备和计算类型
    if device == "auto":
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    
    if compute_type == "auto":
        if device == "cuda":
            compute_type = "float16"
        else:
            compute_type = "int8"
    
    print(f"Loading model: {model_size} on {device} ({compute_type})", file=sys.stderr)
    
    # 加载模型
    model = WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
        download_root=os.path.join(os.path.dirname(__file__), "..", "models", "whisper")
    )
    
    # VAD 参数
    vad_parameters = None
    if use_vad:
        vad_parameters = {
            "min_silence_duration_ms": vad_min_silence_ms,
            "speech_pad_ms": vad_speech_pad_ms,
            "threshold": 0.5
        }
        print(f"VAD enabled: min_silence={vad_min_silence_ms}ms", file=sys.stderr)
    
    # 转录
    print("Starting transcription...", file=sys.stderr)
    
    segments_generator, info = model.transcribe(
        audio_path,
        language=language,
        task="transcribe",
        beam_size=beam_size,
        best_of=best_of,
        temperature=temperature,
        word_timestamps=word_timestamps,
        condition_on_previous_text=condition_on_previous,
        initial_prompt=initial_prompt,
        vad_filter=use_vad,
        vad_parameters=vad_parameters
    )
    
    # 收集结果
    segments = []
    full_text = []
    
    for segment in segments_generator:
        seg_data = {
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip(),
        }
        
        # 添加词级时间戳
        if word_timestamps and segment.words:
            seg_data["words"] = [
                {
                    "word": word.word,
                    "start": word.start,
                    "end": word.end,
                    "probability": word.probability
                }
                for word in segment.words
            ]
            # 计算平均置信度
            seg_data["confidence"] = sum(w.probability for w in segment.words) / len(segment.words)
        
        segments.append(seg_data)
        full_text.append(segment.text.strip())
        
        # 进度输出
        print(f"  [{segment.start:.1f}s - {segment.end:.1f}s] {segment.text.strip()[:50]}...", file=sys.stderr)
    
    print(f"Transcription complete: {len(segments)} segments", file=sys.stderr)
    
    # 质量评估
    quality_metrics = evaluate_asr_quality(segments)
    print(f"Quality score: {quality_metrics['quality_score']}", file=sys.stderr)
    
    return {
        "segments": segments,
        "text": " ".join(full_text),
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "quality_metrics": quality_metrics
    }


def smart_post_process(segments: list, 
                       min_segment_duration: float = 1.0,
                       max_segment_duration: float = 10.0,
                       min_words: int = 3,
                       max_words: int = 25) -> list:
    """
    智能后处理：合并过短段落，拆分过长段落
    
    Args:
        segments: 原始段落
        min_segment_duration: 最小段落时长（秒）
        max_segment_duration: 最大段落时长（秒）
        min_words: 最小词数
        max_words: 最大词数
        
    Returns:
        处理后的段落
    """
    if not segments:
        return segments
    
    processed = []
    current = None
    
    for seg in segments:
        text = seg.get("text", "").strip()
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        duration = end - start
        word_count = len(text.split())
        
        if not text:
            continue
        
        # 初始化
        if current is None:
            current = {
                "start": start,
                "end": end,
                "text": text,
                "words": seg.get("words", [])
            }
            continue
        
        current_duration = current["end"] - current["start"]
        current_words = len(current["text"].split())
        gap = start - current["end"]
        
        # 判断是否合并
        should_merge = False
        
        # 当前段落太短
        if current_duration < min_segment_duration or current_words < min_words:
            should_merge = True
        
        # 新段落太短且间隔小
        if (duration < min_segment_duration or word_count < min_words) and gap < 0.5:
            should_merge = True
        
        # 检查合并后是否超限
        merged_duration = end - current["start"]
        merged_words = current_words + word_count
        
        if should_merge and merged_duration <= max_segment_duration and merged_words <= max_words:
            # 合并
            current["end"] = end
            current["text"] = current["text"] + " " + text
            if seg.get("words"):
                current["words"].extend(seg["words"])
        else:
            # 保存当前，开始新段
            processed.append(current)
            current = {
                "start": start,
                "end": end,
                "text": text,
                "words": seg.get("words", [])
            }
    
    if current:
        processed.append(current)
    
    # 拆分过长段落
    final = []
    for seg in processed:
        if len(seg["text"].split()) > max_words:
            split_segs = _split_long_segment(seg, max_words)
            final.extend(split_segs)
        else:
            final.append(seg)
    
    print(f"Post-processing: {len(segments)} -> {len(final)} segments", file=sys.stderr)
    return final


def _split_long_segment(segment: dict, max_words: int) -> list:
    """拆分过长段落"""
    text = segment["text"]
    words = text.split()
    start = segment["start"]
    end = segment["end"]
    duration = end - start
    
    if len(words) <= max_words:
        return [segment]
    
    # 按词数拆分
    result = []
    chunk_size = max_words
    
    for i in range(0, len(words), chunk_size):
        chunk_words = words[i:i + chunk_size]
        chunk_text = " ".join(chunk_words)
        
        # 按比例分配时间
        ratio_start = i / len(words)
        ratio_end = min((i + len(chunk_words)) / len(words), 1.0)
        
        result.append({
            "start": start + duration * ratio_start,
            "end": start + duration * ratio_end,
            "text": chunk_text,
            "words": []
        })
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Faster-Whisper ASR with built-in VAD support"
    )
    parser.add_argument("audio_path", help="Path to audio file")
    parser.add_argument("--model", default="base", 
                        help="Model size (tiny/base/small/medium/large-v2/large-v3)")
    parser.add_argument("--device", default="auto", help="Device (auto/cuda/cpu)")
    parser.add_argument("--compute_type", default="auto", 
                        help="Compute type (auto/float16/int8)")
    parser.add_argument("--language", default=None, help="Language code")
    parser.add_argument("--use_vad", default="true", help="Use VAD filter")
    parser.add_argument("--vad_min_silence", type=int, default=500,
                        help="VAD min silence duration (ms)")
    parser.add_argument("--word_timestamps", default="true", 
                        help="Generate word-level timestamps")
    parser.add_argument("--temperature", type=float, default=0.0,
                        help="Sampling temperature")
    parser.add_argument("--beam_size", type=int, default=5, help="Beam size")
    parser.add_argument("--post_process", default="true", 
                        help="Apply smart post-processing")
    parser.add_argument("--output", default=None, help="Output JSON file")
    
    args = parser.parse_args()
    
    try:
        # 转录
        result = transcribe_with_faster_whisper(
            args.audio_path,
            model_size=args.model,
            device=args.device,
            compute_type=args.compute_type,
            language=args.language,
            use_vad=args.use_vad.lower() == "true",
            vad_min_silence_ms=args.vad_min_silence,
            word_timestamps=args.word_timestamps.lower() == "true",
            temperature=args.temperature,
            beam_size=args.beam_size
        )
        
        # 后处理
        if args.post_process.lower() == "true":
            try:
                # 使用增强的后处理模块
                from video_tool.core.asr_post_processor import (
                    full_optimization_pipeline, 
                    evaluate_segment_quality
                )
                result["segments"], metrics = full_optimization_pipeline(
                    result["segments"],
                    min_duration=1.5,
                    max_duration=8.0,
                    min_words=4,
                    max_words=20,
                    verbose=True
                )
                result["quality_metrics"] = metrics
            except ImportError:
                # 回退到简单后处理
                result["segments"] = smart_post_process(result["segments"])
                result["quality_metrics"] = evaluate_asr_quality(result["segments"])
        
        # 输出
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"Results saved to: {args.output}", file=sys.stderr)
        else:
            # 输出到 stdout
            print(json.dumps(result, ensure_ascii=False))
        
    except ImportError:
        print("Error: faster-whisper not installed", file=sys.stderr)
        print("Install with: pip install faster-whisper", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
