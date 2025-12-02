import re
import os
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class SubtitleManager:
    def __init__(self, engine_type="deepseek", api_key=None, api_url=None):
        """
        Initialize the subtitle manager.
        
        Args:
            engine_type (str): "deepseek" or "custom"
            api_key (str): API key for the translation service
            api_url (str): API URL (for custom engine)
        """
        self.engine_type = engine_type
        self.api_key = api_key
        self.api_url = api_url or "https://api.deepseek.com/v1/chat/completions"
        self.model = "deepseek-chat"
        self.thread_count = 3  # Default thread count
        self.request_interval = 2.0  # 请求间隔（秒）
        self._lock = threading.Lock()

    def parse_srt(self, srt_path):
        """
        Parses an SRT file into a list of dictionaries.
        """
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Regex to split by double newlines, handling potential variations
        blocks = re.split(r'\n\s*\n', content.strip())
        subtitles = []
        
        for block in blocks:
            lines = block.split('\n')
            if len(lines) >= 3:
                index = lines[0]
                time_range = lines[1]
                text = "\n".join(lines[2:])
                subtitles.append({
                    "index": index,
                    "time_range": time_range,
                    "text": text
                })
        return subtitles

    def save_srt(self, subtitles, output_path):
        """
        Saves a list of subtitle dictionaries to an SRT file.
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            for sub in subtitles:
                f.write(f"{sub['index']}\n")
                f.write(f"{sub['time_range']}\n")
                f.write(f"{sub['text']}\n\n")

    def set_engine(self, engine_type, api_key=None, api_url=None, model=None):
        """Update engine settings."""
        self.engine_type = engine_type
        if api_key:
            self.api_key = api_key
        if api_url:
            self.api_url = api_url
        if model:
            self.model = model
    
    def set_thread_count(self, count):
        """Set the number of concurrent translation threads."""
        self.thread_count = max(1, min(count, 10))  # Limit between 1-10
    
    def set_request_interval(self, interval):
        """Set the interval between API requests (in seconds)."""
        self.request_interval = max(0, interval)

    def translate_subtitles(self, subtitles, target_lang="zh", prompt_text=None, progress_callback=None):
        """
        Translates subtitles using AI API or DeepLX with multi-threading support and retry mechanism.
        
        Args:
            subtitles: List of subtitle dictionaries
            target_lang: Target language code
            prompt_text: Custom prompt template (AI only)
            progress_callback: Callback function for progress updates
        """
        # DeepLX doesn't require API key
        if self.engine_type != "deeplx" and not self.api_key:
            raise ValueError("API Key 未设置，请在设置中配置")
        
        total = len(subtitles)
        
        # Use different batch sizes for different engines
        if self.engine_type == "deeplx":
            batch_size = 1  # DeepLX translates one at a time
        else:
            batch_size = 10  # AI can handle batches
        
        # Create batches
        batches = []
        for i in range(0, total, batch_size):
            batch = subtitles[i:i+batch_size]
            batches.append((i, batch))
        
        # Result storage with thread-safe access
        translated_subs = [None] * total
        completed = [0]  # Use list to allow modification in nested function
        failed_batches = []  # Track failed batches for retry
        
        def translate_batch_worker(batch_index, batch, retry_count=0):
            """Worker function for translating a batch with retry support."""
            import time
            batch_texts = [sub['text'] for sub in batch]
            max_retries = 2
            
            try:
                # 请求间隔
                if self.request_interval > 0:
                    time.sleep(self.request_interval)
                
                if self.engine_type == "deeplx":
                    translated_texts = self._translate_deeplx(batch_texts, target_lang)
                else:
                    translated_texts = self._translate_batch(batch_texts, target_lang, prompt_text)
                
                # Validate translation results
                if not translated_texts or len(translated_texts) != len(batch_texts):
                    raise ValueError(f"Translation result count mismatch: expected {len(batch_texts)}, got {len(translated_texts) if translated_texts else 0}")
                
                # Check if any translation is empty or same as original (potential failure)
                for i, (original, translated) in enumerate(zip(batch_texts, translated_texts)):
                    if not translated or not translated.strip():
                        print(f"警告: 批次 {batch_index} 第 {i+1} 条翻译为空，使用原文")
                        translated_texts[i] = original
                    elif translated == original and len(original) > 10:
                        # If translation is same as original for long text, might be a failure
                        print(f"警告: 批次 {batch_index} 第 {i+1} 条可能未翻译")
                
                # Store results
                for j, sub in enumerate(batch):
                    new_sub = sub.copy()
                    new_sub['text'] = translated_texts[j]
                    
                    with self._lock:
                        translated_subs[batch_index + j] = new_sub
                        completed[0] += 1
                        if progress_callback:
                            progress_callback(completed[0], total)
                
                return True
                
            except Exception as e:
                error_msg = f"批次 {batch_index} 翻译失败 (尝试 {retry_count + 1}/{max_retries + 1}): {e}"
                print(error_msg)
                
                # Retry logic
                if retry_count < max_retries:
                    print(f"正在重试批次 {batch_index}...")
                    import time
                    time.sleep(1)  # Wait before retry
                    return translate_batch_worker(batch_index, batch, retry_count + 1)
                else:
                    # Final fallback: keep original text
                    print(f"批次 {batch_index} 重试失败，保留原文")
                    with self._lock:
                        for j, sub in enumerate(batch):
                            translated_subs[batch_index + j] = sub.copy()
                            completed[0] += 1
                            if progress_callback:
                                progress_callback(completed[0], total)
                        failed_batches.append(batch_index)
                    return False
        
        # Use ThreadPoolExecutor for concurrent translation
        print(f"开始多线程翻译，并发数: {self.thread_count}")
        with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
            futures = {
                executor.submit(translate_batch_worker, batch_index, batch): batch_index 
                for batch_index, batch in batches
            }
            
            # Wait for all tasks to complete
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"线程执行错误: {e}")
        
        # Check for None values (shouldn't happen, but safety check)
        none_count = sum(1 for sub in translated_subs if sub is None)
        if none_count > 0:
            print(f"警告: 发现 {none_count} 条未翻译的字幕，使用原文填充")
            for i, sub in enumerate(translated_subs):
                if sub is None:
                    translated_subs[i] = subtitles[i].copy()
        
        # Summary
        if failed_batches:
            print(f"翻译完成，但有 {len(failed_batches)} 个批次失败（已保留原文）")
        else:
            print("所有字幕翻译成功！")
        
        return translated_subs
    
    def _translate_deeplx(self, texts, target_lang):
        """Translate using DeepLX API."""
        # Map language codes to DeepL format
        lang_map = {
            "zh": "ZH",
            "en": "EN",
            "ja": "JA",
            "ko": "KO",
            "de": "DE",
            "fr": "FR",
            "es": "ES",
            "ru": "RU"
        }
        target = lang_map.get(target_lang, target_lang.upper())
        
        # Build API URL
        if self.api_key:
            url = f"https://api.deeplx.org/{self.api_key}/translate"
        else:
            url = "https://api.deeplx.org/translate"
        
        translated = []
        for text in texts:
            payload = {
                "text": text,
                "source_lang": "auto",
                "target_lang": target
            }
            
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("code") == 200:
                        translated.append(result.get("data", text))
                    else:
                        print(f"DeepLX error: {result}")
                        translated.append(text)
                else:
                    print(f"DeepLX request failed: {response.status_code}")
                    translated.append(text)
            except Exception as e:
                print(f"DeepLX error: {e}")
                translated.append(text)
        
        return translated

    def _translate_batch(self, texts, target_lang, prompt_text=None):
        """Translate a batch of texts using the configured API with context awareness."""
        # 使用上下文感知翻译
        return self._translate_with_context(texts, target_lang, prompt_text)
    
    def _translate_with_context(self, texts, target_lang, prompt_text=None):
        """
        上下文感知的翻译：批量翻译保持上下文连贯性
        
        通过将多个片段合并翻译，让 AI 理解上下文关系，
        产生更连贯、更自然的翻译结果。
        """
        # Build the prompt
        if prompt_text:
            system_prompt = prompt_text
        else:
            lang_names = {
                "zh": "中文", "ja": "日语", "ko": "韩语",
                "en": "英语", "de": "德语", "fr": "法语"
            }
            lang_name = lang_names.get(target_lang, target_lang)
            system_prompt = f"""你是一个专业的字幕翻译器。请将以下字幕翻译成{lang_name}。

翻译要求：
1. 保持原有的语气和风格，翻译要自然流畅
2. 注意上下文连贯性，前后句子的翻译要衔接自然
3. 专有名词、人名等保持一致的翻译
4. 口语化表达要翻译得自然，不要过于书面化
5. 保持原文的情感色彩和语气"""
        
        # 上下文感知翻译策略：使用分隔符合并翻译
        SEPARATOR = " ||| "
        
        # 合并文本，保持上下文
        combined_text = SEPARATOR.join(texts)
        
        # 格式要求
        format_instruction = f"""
输出格式要求：
- 输入共 {len(texts)} 条字幕，用 " ||| " 分隔
- 输出也必须是 {len(texts)} 条翻译，用 " ||| " 分隔
- 保持与输入完全相同的分隔符和数量
- 不要添加序号、换行或其他格式
- 直接输出翻译结果，用 " ||| " 分隔

示例：
输入: Hello ||| How are you ||| Nice to meet you
输出: 你好 ||| 你好吗 ||| 很高兴认识你"""
        
        user_message = f"""请翻译以下 {len(texts)} 条连续的字幕（注意保持上下文连贯）：

{combined_text}

{format_instruction}"""
        
        # Call API
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.3
        }
        
        response = requests.post(
            self.api_url,
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code != 200:
            raise RuntimeError(f"API 请求失败 ({response.status_code}): {response.text}")
        
        result = response.json()
        content = result['choices'][0]['message']['content'].strip()
        
        # 解析响应 - 按分隔符切分
        translated = self._parse_context_response(content, texts, SEPARATOR)
        
        return translated
    
    def _parse_context_response(self, content, original_texts, separator=" ||| "):
        """
        解析上下文感知翻译的响应
        """
        expected_count = len(original_texts)
        
        # 方法1: 直接按分隔符切分
        if separator in content:
            parts = content.split(separator)
            # 清理每个部分
            translated = [p.strip() for p in parts if p.strip()]
            
            if len(translated) == expected_count:
                return translated
            
            # 如果数量接近，尝试修复
            if abs(len(translated) - expected_count) <= 2:
                print(f"上下文翻译数量略有偏差: {len(translated)} vs {expected_count}")
                return self._fix_translation_count(translated, original_texts)
        
        # 方法2: 尝试其他可能的分隔符
        for alt_sep in ['|||', ' | ', '|', '\n']:
            if alt_sep in content and alt_sep != separator:
                parts = content.split(alt_sep)
                translated = [p.strip() for p in parts if p.strip()]
                if len(translated) == expected_count:
                    print(f"使用备选分隔符 '{alt_sep}' 成功解析")
                    return translated
        
        # 方法3: 回退到按行解析
        print("上下文翻译格式异常，回退到按行解析")
        return self._parse_numbered_response(content, expected_count)
    
    def _fix_translation_count(self, translated, original_texts):
        """
        修复翻译数量不匹配的问题
        """
        expected_count = len(original_texts)
        
        # 如果翻译太少，用原文补充
        while len(translated) < expected_count:
            idx = len(translated)
            print(f"  补充第 {idx+1} 条: 使用原文")
            translated.append(original_texts[idx])
        
        # 如果翻译太多，截断
        if len(translated) > expected_count:
            print(f"  截断多余的 {len(translated) - expected_count} 条翻译")
            translated = translated[:expected_count]
        
        return translated
    
    def _translate_batch_legacy(self, texts, target_lang, prompt_text=None):
        """
        传统的批量翻译方法（备用）
        """
        # Build the prompt
        if prompt_text:
            system_prompt = prompt_text
        else:
            lang_name = "中文" if target_lang == "zh" else "English"
            system_prompt = f"你是一个专业的字幕翻译器。请将以下字幕翻译成{lang_name}。保持原有的语气和风格，翻译要自然流畅。只返回翻译结果，每行对应一条字幕，不要添加序号或其他内容。"
        
        # 强调格式要求的提示
        format_instruction = f"""
重要格式要求：
- 输入共 {len(texts)} 条字幕，你必须输出恰好 {len(texts)} 行翻译
- 每行翻译对应一条原文，按顺序一一对应
- 使用 "1. 翻译内容" 的格式，序号必须从1到{len(texts)}
- 不要合并、拆分或跳过任何一条
- 如果某条原文很短或是语气词，也要单独翻译成一行
"""
        
        # Format input texts with clear numbering
        numbered_texts = "\n".join([f"{i+1}. {text}" for i, text in enumerate(texts)])
        user_message = f"请翻译以下 {len(texts)} 条字幕（必须输出 {len(texts)} 行）：\n\n{numbered_texts}\n\n{format_instruction}"
        
        # Call API
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.3
        }
        
        response = requests.post(
            self.api_url,
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code != 200:
            raise RuntimeError(f"API 请求失败 ({response.status_code}): {response.text}")
        
        result = response.json()
        content = result['choices'][0]['message']['content']
        
        # 解析响应 - 优先按序号匹配
        translated = self._parse_numbered_response(content, len(texts))
        
        # 验证数量
        if len(translated) != len(texts):
            print(f"警告: 翻译结果数量不匹配 (期望 {len(texts)}, 实际 {len(translated)})")
            print(f"原始响应:\n{content[:500]}...")
            
            # 尝试修复
            while len(translated) < len(texts):
                idx = len(translated)
                print(f"  补充第 {idx+1} 条: 使用原文")
                translated.append(texts[idx])
        
        return translated[:len(texts)]
    
    def _parse_numbered_response(self, content, expected_count):
        """
        解析带序号的翻译响应，确保按序号正确匹配
        """
        lines = content.strip().split('\n')
        
        # 方法1: 尝试按序号提取
        numbered_results = {}
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 匹配 "1. xxx" 或 "1、xxx" 或 "1: xxx" 格式
            match = re.match(r'^(\d+)[\.\、\:\s]+(.+)$', line)
            if match:
                num = int(match.group(1))
                text = match.group(2).strip()
                if 1 <= num <= expected_count and text:
                    numbered_results[num] = text
        
        # 如果按序号提取成功且数量正确
        if len(numbered_results) == expected_count:
            return [numbered_results[i] for i in range(1, expected_count + 1)]
        
        # 方法2: 如果序号提取不完整，按行顺序提取
        translated = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 移除可能的序号前缀
            cleaned = re.sub(r'^\d+[\.\、\:\s]+', '', line)
            if cleaned:
                translated.append(cleaned)
        
        return translated

    def _mock_translate(self, text, target_lang):
        """Mock translation for testing (when no API key)."""
        if target_lang == "zh":
            return f"[中] {text}"
        elif target_lang == "en":
            return f"[EN] {text}"
        return text

    def merge_subtitles(self, top_subs, bottom_subs):
        """
        Merges two subtitle tracks for dual-language display.
        First parameter (top_subs) will be on top, second (bottom_subs) on bottom.
        
        Args:
            top_subs: Subtitles to show on top (e.g., translated Chinese)
            bottom_subs: Subtitles to show on bottom (e.g., original English)
        """
        merged = []
        for top, bottom in zip(top_subs, bottom_subs):
            new_sub = top.copy()
            new_sub['text'] = f"{top['text']}\n{bottom['text']}"
            merged.append(new_sub)
        return merged

    def align_translation_timestamps(self, original_segments, translated_texts, 
                                      target_lang="zh", speaker_rate=1.0):
        """
        将翻译后的文本与原始时间戳对齐，为 TTS 准备
        
        Args:
            original_segments: 原始字幕段落列表 [{"text": str, "time_range": str, ...}, ...]
            translated_texts: 翻译后的文本列表 [str, ...]
            target_lang: 目标语言
            speaker_rate: 说话速度倍率 (1.0 = 正常)
            
        Returns:
            对齐后的字幕列表，包含时间戳估算
        """
        aligned_results = []
        
        # 不同语言的平均字符/秒速率（用于估算）
        # 中文约 3-4 字/秒，英文约 12-15 字符/秒
        lang_char_rates = {
            "zh": 3.5,  # 中文字/秒
            "ja": 4.0,  # 日语字/秒
            "ko": 4.0,  # 韩语字/秒
            "en": 14.0,  # 英语字符/秒
        }
        target_rate = lang_char_rates.get(target_lang, 4.0) * speaker_rate
        
        for i, (orig, trans) in enumerate(zip(original_segments, translated_texts)):
            # 解析原始时间戳
            time_range = orig.get('time_range', '00:00:00,000 --> 00:00:00,000')
            start_time, end_time = self._parse_time_range(time_range)
            orig_duration = end_time - start_time
            
            orig_text = orig.get('text', '')
            trans_text = trans if isinstance(trans, str) else trans.get('text', '')
            
            # 计算原始语速（字符/秒）
            if orig_duration > 0 and len(orig_text) > 0:
                orig_chars_per_second = len(orig_text) / orig_duration
            else:
                orig_chars_per_second = 14.0  # 默认英语速率
            
            # 估算翻译文本所需时长
            estimated_duration = len(trans_text) / target_rate
            
            # 时间戳对齐策略
            aligned_segment = self._calculate_aligned_timestamps(
                start_time, end_time, orig_duration,
                orig_text, trans_text,
                estimated_duration, target_rate
            )
            
            aligned_segment['index'] = orig.get('index', str(i + 1))
            aligned_segment['original_text'] = orig_text
            aligned_segment['original_duration'] = orig_duration
            
            aligned_results.append(aligned_segment)
        
        # 后处理：确保时间戳不重叠
        aligned_results = self._fix_timestamp_overlaps(aligned_results)
        
        return aligned_results
    
    def _parse_time_range(self, time_range):
        """
        解析 SRT 时间范围字符串
        
        Args:
            time_range: "00:00:01,500 --> 00:00:04,200"
            
        Returns:
            (start_seconds, end_seconds)
        """
        parts = time_range.split(' --> ')
        if len(parts) != 2:
            return 0.0, 0.0
        
        def parse_timestamp(ts):
            ts = ts.strip()
            # 格式: HH:MM:SS,mmm
            match = re.match(r'(\d+):(\d+):(\d+)[,.](\d+)', ts)
            if match:
                h, m, s, ms = map(int, match.groups())
                return h * 3600 + m * 60 + s + ms / 1000.0
            return 0.0
        
        return parse_timestamp(parts[0]), parse_timestamp(parts[1])
    
    def _format_timestamp(self, seconds):
        """
        将秒数格式化为 SRT 时间戳
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    def _calculate_aligned_timestamps(self, start_time, end_time, orig_duration,
                                       orig_text, trans_text, estimated_duration, target_rate):
        """
        计算对齐后的时间戳
        
        策略：
        1. 如果翻译文本较短，保持原始时间戳
        2. 如果翻译文本较长，适当延长结束时间（但不超过下一段开始）
        3. 考虑 TTS 的实际播放速度
        """
        # 计算时长比例
        duration_ratio = estimated_duration / orig_duration if orig_duration > 0 else 1.0
        
        # 基础策略：保持开始时间不变
        new_start = start_time
        
        if duration_ratio <= 1.0:
            # 翻译较短或相当，保持原始结束时间
            new_end = end_time
            speed_adjustment = 1.0
        elif duration_ratio <= 1.3:
            # 翻译稍长（30%以内），轻微延长
            extension = (estimated_duration - orig_duration) * 0.5
            new_end = end_time + extension
            speed_adjustment = 1.0
        else:
            # 翻译明显较长，需要调整语速或延长时间
            # 策略：延长时间 + 建议加速
            max_extension = orig_duration * 0.5  # 最多延长50%
            extension = min(estimated_duration - orig_duration, max_extension)
            new_end = end_time + extension
            
            # 计算建议的语速调整
            actual_duration = new_end - new_start
            speed_adjustment = estimated_duration / actual_duration
        
        return {
            'text': trans_text,
            'start': new_start,
            'end': new_end,
            'time_range': f"{self._format_timestamp(new_start)} --> {self._format_timestamp(new_end)}",
            'duration': new_end - new_start,
            'estimated_tts_duration': estimated_duration,
            'speed_adjustment': round(speed_adjustment, 2),  # TTS 建议语速
            'duration_ratio': round(duration_ratio, 2)
        }
    
    def _fix_timestamp_overlaps(self, segments):
        """
        修复时间戳重叠问题
        """
        if len(segments) < 2:
            return segments
        
        fixed = []
        for i, seg in enumerate(segments):
            if i == 0:
                fixed.append(seg)
                continue
            
            prev_end = fixed[-1]['end']
            curr_start = seg['start']
            
            # 如果当前段开始时间早于上一段结束时间
            if curr_start < prev_end:
                # 调整上一段的结束时间
                gap = 0.1  # 保留 100ms 间隔
                new_prev_end = curr_start - gap
                
                if new_prev_end > fixed[-1]['start']:
                    fixed[-1]['end'] = new_prev_end
                    fixed[-1]['time_range'] = (
                        f"{self._format_timestamp(fixed[-1]['start'])} --> "
                        f"{self._format_timestamp(new_prev_end)}"
                    )
                    fixed[-1]['duration'] = new_prev_end - fixed[-1]['start']
            
            fixed.append(seg)
        
        return fixed
    
    def export_tts_alignment_data(self, aligned_segments, output_path=None):
        """
        导出 TTS 对齐数据为 JSON 格式
        
        Args:
            aligned_segments: align_translation_timestamps 的输出
            output_path: 输出文件路径（可选）
            
        Returns:
            dict: TTS 对齐数据
        """
        # 计算总时长
        if aligned_segments:
            total_duration = max(seg['end'] for seg in aligned_segments)
        else:
            total_duration = 0
        
        # 构建输出数据
        tts_data = {
            "metadata": {
                "total_duration": round(total_duration, 2),
                "segment_count": len(aligned_segments),
                "format_version": "1.0"
            },
            "segments": []
        }
        
        for seg in aligned_segments:
            segment_data = {
                "index": seg.get('index', ''),
                "text": seg.get('text', ''),
                "start": round(seg.get('start', 0), 3),
                "end": round(seg.get('end', 0), 3),
                "duration": round(seg.get('duration', 0), 3),
                "speed_adjustment": seg.get('speed_adjustment', 1.0),
                "original_text": seg.get('original_text', ''),
                "original_duration": round(seg.get('original_duration', 0), 3)
            }
            tts_data["segments"].append(segment_data)
        
        # 保存到文件（如果指定）
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(tts_data, f, ensure_ascii=False, indent=2)
            print(f"TTS 对齐数据已保存到: {output_path}")
        
        return tts_data

if __name__ == "__main__":
    # Test
    pass
