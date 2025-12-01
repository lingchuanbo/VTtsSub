import argparse
import json
import os
import sys
import warnings

# Filter warnings to keep output clean
warnings.filterwarnings("ignore")


def load_silero_vad():
    """加载 Silero VAD 模型"""
    import torch
    
    # 使用 torch.hub 加载 Silero VAD
    model, utils = torch.hub.load(
        repo_or_dir='snakers4/silero-vad',
        model='silero_vad',
        force_reload=False,
        onnx=False,
        trust_repo=True
    )
    
    (get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils
    
    return model, get_speech_timestamps, read_audio


def get_vad_segments(audio_path, vad_model, get_speech_timestamps, read_audio, 
                     threshold=0.5, min_speech_duration_ms=250, min_silence_duration_ms=100):
    """
    使用 Silero VAD 获取语音活动时间段
    
    Args:
        audio_path: 音频文件路径
        vad_model: Silero VAD 模型
        get_speech_timestamps: VAD 工具函数
        read_audio: 音频读取函数
        threshold: VAD 阈值 (0-1)，越高越严格
        min_speech_duration_ms: 最小语音段时长（毫秒）
        min_silence_duration_ms: 最小静音时长（毫秒）
        
    Returns:
        list: 语音时间段列表 [{"start": float, "end": float}, ...]
    """
    import torch
    
    SAMPLING_RATE = 16000
    
    # 读取音频
    wav = read_audio(audio_path, sampling_rate=SAMPLING_RATE)
    
    # 获取语音时间戳
    speech_timestamps = get_speech_timestamps(
        wav, 
        vad_model,
        threshold=threshold,
        sampling_rate=SAMPLING_RATE,
        min_speech_duration_ms=min_speech_duration_ms,
        min_silence_duration_ms=min_silence_duration_ms,
        return_seconds=True  # 返回秒数而非采样点
    )
    
    return speech_timestamps


def filter_hallucinations(segments, vad_segments, tolerance=0.5):
    """
    使用 VAD 结果过滤 Whisper 的幻觉
    
    Args:
        segments: Whisper 返回的 segments
        vad_segments: VAD 检测到的语音段
        tolerance: 时间容差（秒）
        
    Returns:
        过滤后的 segments
    """
    if not vad_segments:
        return segments
    
    filtered = []
    
    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)
        seg_text = seg.get("text", "").strip()
        
        # 跳过空文本
        if not seg_text:
            continue
        
        # 检查该段是否与任何 VAD 语音段重叠
        has_speech = False
        for vad_seg in vad_segments:
            vad_start = vad_seg.get("start", 0)
            vad_end = vad_seg.get("end", 0)
            
            # 检查重叠（带容差）
            overlap_start = max(seg_start, vad_start - tolerance)
            overlap_end = min(seg_end, vad_end + tolerance)
            
            if overlap_end > overlap_start:
                has_speech = True
                break
        
        if has_speech:
            filtered.append(seg)
        else:
            # 可能是幻觉，记录日志
            print(f"[VAD] 过滤可能的幻觉: [{seg_start:.2f}-{seg_end:.2f}] {seg_text[:50]}...", file=sys.stderr)
    
    return filtered


def adjust_timestamps_with_vad(segments, vad_segments, tolerance=0.3):
    """
    使用 VAD 结果调整 Whisper 的时间戳
    
    Args:
        segments: Whisper 返回的 segments
        vad_segments: VAD 检测到的语音段
        tolerance: 时间容差（秒）
        
    Returns:
        调整后的 segments
    """
    if not vad_segments:
        return segments
    
    adjusted = []
    
    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)
        
        # 找到最匹配的 VAD 段
        best_vad = None
        best_overlap = 0
        
        for vad_seg in vad_segments:
            vad_start = vad_seg.get("start", 0)
            vad_end = vad_seg.get("end", 0)
            
            # 计算重叠
            overlap_start = max(seg_start, vad_start)
            overlap_end = min(seg_end, vad_end)
            overlap = max(0, overlap_end - overlap_start)
            
            if overlap > best_overlap:
                best_overlap = overlap
                best_vad = vad_seg
        
        # 如果找到匹配的 VAD 段，微调时间戳
        if best_vad and best_overlap > 0:
            vad_start = best_vad.get("start", 0)
            vad_end = best_vad.get("end", 0)
            
            # 如果 Whisper 开始时间早于 VAD，调整到 VAD 开始
            if seg_start < vad_start - tolerance:
                seg["start"] = vad_start
            
            # 如果 Whisper 结束时间晚于 VAD，调整到 VAD 结束
            if seg_end > vad_end + tolerance:
                seg["end"] = vad_end
        
        adjusted.append(seg)
    
    return adjusted


def detect_repetition_loops(segments, max_repetitions=3):
    """
    检测并移除 Whisper 的循环重复错误
    
    Args:
        segments: Whisper 返回的 segments
        max_repetitions: 允许的最大重复次数
        
    Returns:
        清理后的 segments
    """
    if len(segments) < 2:
        return segments
    
    cleaned = []
    prev_text = ""
    repetition_count = 0
    
    for seg in segments:
        text = seg.get("text", "").strip().lower()
        
        # 检查是否与前一段相同或非常相似
        if text == prev_text or (len(text) > 10 and text in prev_text):
            repetition_count += 1
            if repetition_count >= max_repetitions:
                print(f"[VAD] 检测到循环重复，跳过: {text[:50]}...", file=sys.stderr)
                continue
        else:
            repetition_count = 0
        
        cleaned.append(seg)
        prev_text = text
    
    return cleaned


def main():
    parser = argparse.ArgumentParser(description="Run Whisper ASR in a separate process with Silero-VAD")
    parser.add_argument("audio_path", help="Path to the input audio file")
    parser.add_argument("--model", default="base", help="Whisper model size")
    parser.add_argument("--language", default=None, help="Language code")
    parser.add_argument("--model_dir", default=None, help="Custom model directory")
    parser.add_argument("--use_vad", default="true", help="Use Silero-VAD for better accuracy")
    parser.add_argument("--vad_threshold", type=float, default=0.5, help="VAD threshold (0-1)")
    
    args = parser.parse_args()
    use_vad = args.use_vad.lower() == "true"
    
    try:
        # Set model directory if provided
        if args.model_dir:
            os.environ['WHISPER_CACHE_DIR'] = args.model_dir
            
        import whisper
        import torch
        
        # Check if CUDA is available
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {device}", file=sys.stderr)
        
        # 加载 Silero VAD（如果启用）
        vad_segments = None
        if use_vad:
            try:
                print("Loading Silero-VAD model...", file=sys.stderr)
                vad_model, get_speech_timestamps, read_audio = load_silero_vad()
                
                print("Running VAD analysis...", file=sys.stderr)
                vad_segments = get_vad_segments(
                    args.audio_path, 
                    vad_model, 
                    get_speech_timestamps, 
                    read_audio,
                    threshold=args.vad_threshold
                )
                print(f"VAD detected {len(vad_segments)} speech segments", file=sys.stderr)
                
            except Exception as e:
                print(f"Warning: VAD failed, continuing without it: {e}", file=sys.stderr)
                vad_segments = None
        
        # Load Whisper model
        print(f"Loading Whisper model: {args.model}...", file=sys.stderr)
        model = whisper.load_model(args.model, download_root=args.model_dir, device=device)
        
        # Transcribe with word-level timestamps for precise timing
        # 使用 VAD 相关参数提升准确性
        transcribe_options = {
            "language": args.language if args.language and args.language != "None" else None,
            "word_timestamps": True,  # 启用词级时间戳
            "condition_on_previous_text": True,  # 基于上下文提升连贯性
            "no_speech_threshold": 0.6,  # 静音检测阈值
            "logprob_threshold": -1.0,  # 对数概率阈值，过滤低置信度
            "compression_ratio_threshold": 2.4,  # 压缩比阈值，检测重复
        }
        
        # 如果有 VAD 结果，可以使用更严格的参数
        if vad_segments:
            transcribe_options["no_speech_threshold"] = 0.5
        
        print("Starting transcription...", file=sys.stderr)
        result = model.transcribe(args.audio_path, **transcribe_options)
        
        segments = result["segments"]
        
        # 使用 VAD 结果优化
        if vad_segments:
            print("Filtering hallucinations with VAD...", file=sys.stderr)
            segments = filter_hallucinations(segments, vad_segments)
            
            print("Adjusting timestamps with VAD...", file=sys.stderr)
            segments = adjust_timestamps_with_vad(segments, vad_segments)
        
        # 检测并移除循环重复
        print("Detecting repetition loops...", file=sys.stderr)
        segments = detect_repetition_loops(segments)
        
        # Output result as JSON
        output = {
            "segments": segments,
            "text": result["text"],
            "vad_enabled": use_vad and vad_segments is not None,
            "vad_segments_count": len(vad_segments) if vad_segments else 0
        }
        
        # Print JSON to stdout
        print(json.dumps(output))
        
    except Exception as e:
        # Print error to stderr
        print(f"Error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
