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
        """Translate a batch of texts using the configured API."""
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

if __name__ == "__main__":
    # Test
    pass
