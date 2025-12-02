"""
高级处理模块 - 分情况处理、质量评估与迭代优化

功能：
1. 内容类型检测（对话/演讲/技术内容）
2. 分情况处理策略
3. 质量评估指标（BLEU、时间戳误差、语义连贯性）
4. 迭代优化反馈循环
5. 术语表管理
"""

import re
import json
import os
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
import math


class ContentType:
    """内容类型枚举"""
    DIALOGUE = "dialogue"           # 对话内容
    LECTURE = "lecture"             # 演讲/讲课
    TECHNICAL = "technical"         # 技术内容
    NARRATIVE = "narrative"         # 叙述/旁白
    MIXED = "mixed"                 # 混合类型


class ContentAnalyzer:
    """内容类型分析器"""
    
    # 技术术语模式
    TECHNICAL_PATTERNS = [
        r'\b(API|SDK|HTTP|JSON|XML|SQL|CPU|GPU|RAM|SSD)\b',
        r'\b(function|class|method|variable|parameter|algorithm)\b',
        r'\b(machine learning|deep learning|neural network|AI|ML)\b',
        r'\b(database|server|client|protocol|framework)\b',
        r'\b\d+\.\d+\.\d+\b',  # 版本号
        r'\b[A-Z]{2,}[a-z]+[A-Z]\w*\b',  # 驼峰命名
    ]
    
    # 对话标记模式
    DIALOGUE_PATTERNS = [
        r'\b(I|you|we|they|he|she)\s+(think|believe|feel|want|need)\b',
        r'\b(yes|no|yeah|okay|ok|sure|right|well)\b',
        r'\?$',  # 问句
        r'^(so|and|but|because)\b',
        r'\b(said|asked|replied|answered)\b',
    ]
    
    # 演讲/讲课模式
    LECTURE_PATTERNS = [
        r'\b(today|now|let\'s|let me|I\'ll|we\'ll)\b',
        r'\b(first|second|third|finally|next|then)\b',
        r'\b(important|key|main|essential|fundamental)\b',
        r'\b(example|instance|case|scenario)\b',
        r'\b(understand|learn|know|remember|note)\b',
    ]
    
    def __init__(self):
        self.technical_regex = [re.compile(p, re.IGNORECASE) for p in self.TECHNICAL_PATTERNS]
        self.dialogue_regex = [re.compile(p, re.IGNORECASE) for p in self.DIALOGUE_PATTERNS]
        self.lecture_regex = [re.compile(p, re.IGNORECASE) for p in self.LECTURE_PATTERNS]
    
    def analyze(self, segments: List[Dict]) -> Dict[str, Any]:
        """
        分析内容类型
        
        Args:
            segments: 字幕段落列表
            
        Returns:
            {
                "content_type": ContentType,
                "confidence": float,
                "scores": {"dialogue": float, "lecture": float, "technical": float},
                "detected_terms": List[str],
                "speaker_changes": int
            }
        """
        all_text = " ".join([seg.get("text", "") for seg in segments])
        
        # 计算各类型得分
        dialogue_score = self._calculate_pattern_score(all_text, self.dialogue_regex)
        lecture_score = self._calculate_pattern_score(all_text, self.lecture_regex)
        technical_score = self._calculate_pattern_score(all_text, self.technical_regex)
        
        # 检测说话人变化（简单启发式）
        speaker_changes = self._detect_speaker_changes(segments)
        
        # 检测技术术语
        detected_terms = self._extract_technical_terms(all_text)
        
        # 根据得分判断内容类型
        scores = {
            "dialogue": dialogue_score + (speaker_changes * 0.1),
            "lecture": lecture_score,
            "technical": technical_score + (len(detected_terms) * 0.05)
        }
        
        # 归一化
        total = sum(scores.values()) or 1
        scores = {k: v / total for k, v in scores.items()}
        
        # 确定主要类型
        max_type = max(scores, key=scores.get)
        confidence = scores[max_type]
        
        if confidence < 0.4:
            content_type = ContentType.MIXED
        elif max_type == "dialogue":
            content_type = ContentType.DIALOGUE
        elif max_type == "lecture":
            content_type = ContentType.LECTURE
        else:
            content_type = ContentType.TECHNICAL
        
        return {
            "content_type": content_type,
            "confidence": round(confidence, 3),
            "scores": {k: round(v, 3) for k, v in scores.items()},
            "detected_terms": detected_terms[:20],  # 最多返回20个
            "speaker_changes": speaker_changes
        }
    
    def _calculate_pattern_score(self, text: str, patterns: List) -> float:
        """计算模式匹配得分"""
        score = 0
        word_count = len(text.split()) or 1
        
        for pattern in patterns:
            matches = pattern.findall(text)
            score += len(matches)
        
        # 归一化到 0-1
        return min(score / word_count * 10, 1.0)
    
    def _detect_speaker_changes(self, segments: List[Dict]) -> int:
        """检测说话人变化次数"""
        changes = 0
        prev_style = None
        
        for seg in segments:
            text = seg.get("text", "")
            # 简单启发式：检测问答模式
            is_question = text.strip().endswith("?")
            current_style = "question" if is_question else "statement"
            
            if prev_style and current_style != prev_style:
                changes += 1
            prev_style = current_style
        
        return changes
    
    def _extract_technical_terms(self, text: str) -> List[str]:
        """提取技术术语"""
        terms = set()
        
        for pattern in self.technical_regex:
            matches = pattern.findall(text)
            terms.update(matches)
        
        # 提取大写缩写词
        acronyms = re.findall(r'\b[A-Z]{2,}\b', text)
        terms.update(acronyms)
        
        return list(terms)


class AdaptiveSegmenter:
    """自适应分段器 - 根据内容类型调整分段策略"""
    
    def __init__(self):
        # 不同内容类型的分段参数
        self.strategies = {
            ContentType.DIALOGUE: {
                "min_duration": 1.0,
                "max_duration": 5.0,
                "min_chars": 10,
                "max_chars": 80,
                "split_on_speaker_change": True,
                "merge_short_segments": False
            },
            ContentType.LECTURE: {
                "min_duration": 2.0,
                "max_duration": 10.0,
                "min_chars": 30,
                "max_chars": 150,
                "split_on_speaker_change": False,
                "merge_short_segments": True,
                "sentences_per_segment": 2  # 2-3句话一段
            },
            ContentType.TECHNICAL: {
                "min_duration": 2.0,
                "max_duration": 8.0,
                "min_chars": 20,
                "max_chars": 120,
                "split_on_speaker_change": False,
                "preserve_terms": True,
                "merge_short_segments": True
            },
            ContentType.NARRATIVE: {
                "min_duration": 2.0,
                "max_duration": 8.0,
                "min_chars": 30,
                "max_chars": 120,
                "split_on_speaker_change": False,
                "merge_short_segments": True
            },
            ContentType.MIXED: {
                "min_duration": 1.5,
                "max_duration": 7.0,
                "min_chars": 20,
                "max_chars": 100,
                "split_on_speaker_change": True,
                "merge_short_segments": True
            }
        }
    
    def segment(self, segments: List[Dict], content_type: str, 
                technical_terms: List[str] = None) -> List[Dict]:
        """
        根据内容类型进行自适应分段
        
        Args:
            segments: 原始段落
            content_type: 内容类型
            technical_terms: 技术术语列表（用于保护）
            
        Returns:
            重新分段后的列表
        """
        strategy = self.strategies.get(content_type, self.strategies[ContentType.MIXED])
        
        if content_type == ContentType.DIALOGUE:
            return self._segment_dialogue(segments, strategy)
        elif content_type == ContentType.LECTURE:
            return self._segment_lecture(segments, strategy)
        elif content_type == ContentType.TECHNICAL:
            return self._segment_technical(segments, strategy, technical_terms or [])
        else:
            return self._segment_default(segments, strategy)
    
    def _segment_dialogue(self, segments: List[Dict], strategy: Dict) -> List[Dict]:
        """对话内容分段 - 按说话人切换分段"""
        result = []
        
        for seg in segments:
            text = seg.get("text", "").strip()
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            
            # 检测是否包含多个说话人的内容
            # 简单策略：按问号分割
            if "?" in text and len(text) > strategy["max_chars"]:
                parts = self._split_by_questions(text, start, end)
                result.extend(parts)
            else:
                result.append(seg)
        
        return result
    
    def _segment_lecture(self, segments: List[Dict], strategy: Dict) -> List[Dict]:
        """演讲/讲课分段 - 按语义段落分段（2-3句话）"""
        result = []
        current = None
        sentence_count = 0
        sentences_per_segment = strategy.get("sentences_per_segment", 2)
        
        for seg in segments:
            text = seg.get("text", "").strip()
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            
            # 计算句子数
            sentences = len(re.findall(r'[.!?。！？]', text))
            sentences = max(1, sentences)
            
            if current is None:
                current = {"start": start, "end": end, "text": text}
                sentence_count = sentences
            elif sentence_count + sentences <= sentences_per_segment + 1:
                # 合并
                current["end"] = end
                current["text"] = current["text"] + " " + text
                sentence_count += sentences
            else:
                # 保存当前，开始新段
                result.append(current)
                current = {"start": start, "end": end, "text": text}
                sentence_count = sentences
        
        if current:
            result.append(current)
        
        return result
    
    def _segment_technical(self, segments: List[Dict], strategy: Dict,
                          technical_terms: List[str]) -> List[Dict]:
        """技术内容分段 - 保留专业术语完整性"""
        result = []
        
        # 创建术语保护正则
        if technical_terms:
            term_pattern = re.compile(
                r'\b(' + '|'.join(re.escape(t) for t in technical_terms) + r')\b',
                re.IGNORECASE
            )
        else:
            term_pattern = None
        
        for seg in segments:
            text = seg.get("text", "").strip()
            
            # 检查是否需要拆分
            if len(text) > strategy["max_chars"]:
                # 找到安全的拆分点（不在术语中间）
                parts = self._split_preserving_terms(seg, strategy, term_pattern)
                result.extend(parts)
            else:
                result.append(seg)
        
        return result
    
    def _segment_default(self, segments: List[Dict], strategy: Dict) -> List[Dict]:
        """默认分段策略"""
        result = []
        current = None
        
        for seg in segments:
            text = seg.get("text", "").strip()
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            duration = end - start
            
            if not text:
                continue
            
            if current is None:
                current = {"start": start, "end": end, "text": text}
            elif (len(current["text"]) + len(text) < strategy["max_chars"] and
                  current["end"] - current["start"] + duration < strategy["max_duration"]):
                # 合并
                current["end"] = end
                current["text"] = current["text"] + " " + text
            else:
                result.append(current)
                current = {"start": start, "end": end, "text": text}
        
        if current:
            result.append(current)
        
        return result
    
    def _split_by_questions(self, text: str, start: float, end: float) -> List[Dict]:
        """按问句拆分"""
        parts = re.split(r'(\?)', text)
        result = []
        duration = end - start
        
        current_text = ""
        for i, part in enumerate(parts):
            current_text += part
            if part == "?" or i == len(parts) - 1:
                if current_text.strip():
                    # 按比例分配时间
                    ratio = len(current_text) / len(text)
                    seg_duration = duration * ratio
                    seg_start = start + (duration - seg_duration) * (len(result) / max(1, len(parts) // 2))
                    
                    result.append({
                        "start": seg_start,
                        "end": seg_start + seg_duration,
                        "text": current_text.strip()
                    })
                current_text = ""
        
        return result if result else [{"start": start, "end": end, "text": text}]
    
    def _split_preserving_terms(self, seg: Dict, strategy: Dict, 
                                term_pattern) -> List[Dict]:
        """拆分时保护术语完整性"""
        text = seg.get("text", "")
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        
        # 找到所有术语位置
        protected_ranges = []
        if term_pattern:
            for match in term_pattern.finditer(text):
                protected_ranges.append((match.start(), match.end()))
        
        # 找到安全的拆分点
        max_chars = strategy["max_chars"]
        split_points = []
        
        for i in range(max_chars, len(text), max_chars):
            # 检查是否在保护范围内
            safe = True
            for pstart, pend in protected_ranges:
                if pstart <= i <= pend:
                    safe = False
                    break
            
            if safe:
                # 找最近的空格或标点
                for j in range(i, max(i - 20, 0), -1):
                    if text[j] in ' .,;:':
                        split_points.append(j + 1)
                        break
        
        if not split_points:
            return [seg]
        
        # 执行拆分
        result = []
        prev = 0
        duration = end - start
        
        for point in split_points:
            part_text = text[prev:point].strip()
            if part_text:
                ratio = len(part_text) / len(text)
                result.append({
                    "start": start + (prev / len(text)) * duration,
                    "end": start + (point / len(text)) * duration,
                    "text": part_text
                })
            prev = point
        
        # 最后一部分
        if prev < len(text):
            part_text = text[prev:].strip()
            if part_text:
                result.append({
                    "start": start + (prev / len(text)) * duration,
                    "end": end,
                    "text": part_text
                })
        
        return result if result else [seg]


class QualityEvaluator:
    """质量评估器"""
    
    def __init__(self):
        self.metrics = {}
    
    def evaluate(self, original_segments: List[Dict], translated_segments: List[Dict],
                 aligned_segments: List[Dict] = None, 
                 reference_translation: List[str] = None) -> Dict[str, Any]:
        """
        综合质量评估
        
        Args:
            original_segments: 原始段落
            translated_segments: 翻译后的段落
            aligned_segments: 对齐后的段落（可选）
            reference_translation: 参考翻译（用于 BLEU，可选）
            
        Returns:
            {
                "overall_score": float,
                "bleu_score": float,
                "timestamp_error": float,
                "coherence_score": float,
                "fragmentation_score": float,
                "details": {...}
            }
        """
        results = {
            "overall_score": 0.0,
            "bleu_score": None,
            "timestamp_error": 0.0,
            "coherence_score": 0.0,
            "fragmentation_score": 0.0,
            "details": {}
        }
        
        # 1. BLEU 分数（如果有参考翻译）
        if reference_translation:
            translated_texts = [seg.get("text", "") for seg in translated_segments]
            results["bleu_score"] = self._calculate_bleu(translated_texts, reference_translation)
        
        # 2. 时间戳对齐误差
        if aligned_segments:
            results["timestamp_error"] = self._calculate_timestamp_error(
                original_segments, aligned_segments
            )
        
        # 3. 语义连贯性评分
        translated_texts = [seg.get("text", "") for seg in translated_segments]
        results["coherence_score"] = self._calculate_coherence(translated_texts)
        
        # 4. 分段碎片化评分
        results["fragmentation_score"] = self._calculate_fragmentation(translated_segments)
        
        # 5. 计算综合得分
        scores = []
        if results["bleu_score"] is not None:
            scores.append(results["bleu_score"])
        
        # 时间戳误差转换为得分（误差越小得分越高）
        timestamp_score = max(0, 1 - results["timestamp_error"] / 0.5)  # 0.5秒以上为0分
        scores.append(timestamp_score)
        scores.append(results["coherence_score"])
        scores.append(1 - results["fragmentation_score"])  # 碎片化越低越好
        
        results["overall_score"] = round(sum(scores) / len(scores), 3) if scores else 0
        
        # 详细信息
        results["details"] = {
            "segment_count": len(translated_segments),
            "avg_segment_length": self._avg_segment_length(translated_segments),
            "timestamp_score": round(timestamp_score, 3)
        }
        
        return results
    
    def _calculate_bleu(self, candidates: List[str], references: List[str]) -> float:
        """
        计算 BLEU 分数（简化版）
        
        使用 n-gram 精确度计算
        """
        if len(candidates) != len(references):
            return 0.0
        
        total_score = 0.0
        
        for cand, ref in zip(candidates, references):
            # 分词
            cand_tokens = cand.lower().split()
            ref_tokens = ref.lower().split()
            
            if not cand_tokens or not ref_tokens:
                continue
            
            # 计算 1-gram 到 4-gram 的精确度
            precisions = []
            for n in range(1, min(5, len(cand_tokens) + 1)):
                cand_ngrams = self._get_ngrams(cand_tokens, n)
                ref_ngrams = self._get_ngrams(ref_tokens, n)
                
                if not cand_ngrams:
                    continue
                
                # 计算匹配数
                matches = sum(min(cand_ngrams[ng], ref_ngrams.get(ng, 0)) 
                             for ng in cand_ngrams)
                precision = matches / sum(cand_ngrams.values())
                precisions.append(precision)
            
            if precisions:
                # 几何平均
                log_precision = sum(math.log(p + 1e-10) for p in precisions) / len(precisions)
                
                # 长度惩罚
                bp = min(1.0, math.exp(1 - len(ref_tokens) / max(len(cand_tokens), 1)))
                
                total_score += bp * math.exp(log_precision)
        
        return round(total_score / max(len(candidates), 1), 3)
    
    def _get_ngrams(self, tokens: List[str], n: int) -> Dict[tuple, int]:
        """获取 n-gram 计数"""
        ngrams = Counter()
        for i in range(len(tokens) - n + 1):
            ngram = tuple(tokens[i:i+n])
            ngrams[ngram] += 1
        return ngrams
    
    def _calculate_timestamp_error(self, original: List[Dict], 
                                   aligned: List[Dict]) -> float:
        """
        计算时间戳对齐误差（秒）
        
        目标：< 100ms
        """
        if not original or not aligned:
            return 0.0
        
        errors = []
        
        for orig, align in zip(original, aligned):
            orig_start = orig.get("start", 0)
            orig_end = orig.get("end", 0)
            align_start = align.get("start", 0)
            align_end = align.get("end", 0)
            
            start_error = abs(orig_start - align_start)
            end_error = abs(orig_end - align_end)
            
            errors.append((start_error + end_error) / 2)
        
        return round(sum(errors) / len(errors), 3) if errors else 0.0
    
    def _calculate_coherence(self, texts: List[str]) -> float:
        """
        计算语义连贯性评分
        
        基于相邻句子的词汇重叠度
        """
        if len(texts) < 2:
            return 1.0
        
        coherence_scores = []
        
        for i in range(1, len(texts)):
            prev_words = set(texts[i-1].lower().split())
            curr_words = set(texts[i].lower().split())
            
            if not prev_words or not curr_words:
                continue
            
            # Jaccard 相似度
            intersection = len(prev_words & curr_words)
            union = len(prev_words | curr_words)
            
            if union > 0:
                coherence_scores.append(intersection / union)
        
        # 连贯性不需要太高，0.1-0.3 是正常范围
        avg_coherence = sum(coherence_scores) / len(coherence_scores) if coherence_scores else 0
        
        # 转换为 0-1 分数（0.2 的重叠度对应 1.0 分）
        return round(min(avg_coherence / 0.2, 1.0), 3)
    
    def _calculate_fragmentation(self, segments: List[Dict]) -> float:
        """
        计算分段碎片化程度
        
        过多短段落 = 高碎片化
        """
        if not segments:
            return 0.0
        
        lengths = [len(seg.get("text", "")) for seg in segments]
        avg_length = sum(lengths) / len(lengths)
        
        # 统计过短段落（< 20 字符）
        short_count = sum(1 for l in lengths if l < 20)
        short_ratio = short_count / len(segments)
        
        # 计算长度方差
        variance = sum((l - avg_length) ** 2 for l in lengths) / len(lengths)
        std_dev = math.sqrt(variance)
        cv = std_dev / avg_length if avg_length > 0 else 0  # 变异系数
        
        # 碎片化分数 = 短段落比例 + 变异系数
        fragmentation = (short_ratio * 0.6 + min(cv, 1) * 0.4)
        
        return round(fragmentation, 3)
    
    def _avg_segment_length(self, segments: List[Dict]) -> float:
        """计算平均段落长度"""
        if not segments:
            return 0.0
        lengths = [len(seg.get("text", "")) for seg in segments]
        return round(sum(lengths) / len(lengths), 1)


class TerminologyManager:
    """术语表管理器"""
    
    def __init__(self, terminology_file: str = None):
        self.terms = {}  # {原文: 译文}
        self.term_file = terminology_file
        
        if terminology_file and os.path.exists(terminology_file):
            self.load(terminology_file)
    
    def load(self, file_path: str):
        """加载术语表"""
        with open(file_path, 'r', encoding='utf-8') as f:
            self.terms = json.load(f)
        print(f"加载了 {len(self.terms)} 个术语")
    
    def save(self, file_path: str = None):
        """保存术语表"""
        path = file_path or self.term_file
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.terms, f, ensure_ascii=False, indent=2)
            print(f"保存了 {len(self.terms)} 个术语到 {path}")
    
    def add_term(self, source: str, target: str):
        """添加术语"""
        self.terms[source.lower()] = target
    
    def get_translation(self, term: str) -> Optional[str]:
        """获取术语翻译"""
        return self.terms.get(term.lower())
    
    def apply_to_text(self, text: str) -> str:
        """应用术语表到文本"""
        result = text
        for source, target in self.terms.items():
            # 使用词边界匹配
            pattern = re.compile(r'\b' + re.escape(source) + r'\b', re.IGNORECASE)
            result = pattern.sub(target, result)
        return result
    
    def extract_and_add(self, segments: List[Dict], analyzer: ContentAnalyzer):
        """从段落中提取并添加新术语"""
        analysis = analyzer.analyze(segments)
        new_terms = analysis.get("detected_terms", [])
        
        added = 0
        for term in new_terms:
            if term.lower() not in self.terms:
                # 默认保留原文（技术术语通常不翻译）
                self.terms[term.lower()] = term
                added += 1
        
        if added > 0:
            print(f"添加了 {added} 个新术语")
        
        return new_terms


class FeedbackLoop:
    """迭代优化反馈循环"""
    
    def __init__(self):
        self.evaluator = QualityEvaluator()
        self.history = []  # 历史评估记录
        
        # 可调参数及其范围
        self.adjustable_params = {
            "merge_threshold": {"min": 0.3, "max": 2.0, "step": 0.1, "current": 1.0},
            "max_segment_chars": {"min": 50, "max": 200, "step": 10, "current": 120},
            "translation_batch_size": {"min": 5, "max": 20, "step": 5, "current": 10},
            "vad_threshold": {"min": 0.3, "max": 0.7, "step": 0.05, "current": 0.5}
        }
        
        # 错误阈值
        self.thresholds = {
            "fragmentation": 0.3,
            "timestamp_error": 0.1,  # 100ms
            "coherence": 0.5,
            "bleu": 0.3
        }
    
    def analyze_errors(self, evaluation: Dict) -> Dict[str, float]:
        """
        分析评估结果中的错误
        
        Returns:
            各类错误的严重程度 (0-1)
        """
        errors = {}
        
        # 碎片化错误
        frag = evaluation.get("fragmentation_score", 0)
        errors["fragmentation"] = frag if frag > self.thresholds["fragmentation"] else 0
        
        # 时间戳错误
        ts_error = evaluation.get("timestamp_error", 0)
        errors["timestamp"] = ts_error / self.thresholds["timestamp_error"] if ts_error > self.thresholds["timestamp_error"] else 0
        
        # 连贯性错误
        coherence = evaluation.get("coherence_score", 1)
        errors["coherence"] = 1 - coherence if coherence < self.thresholds["coherence"] else 0
        
        # 翻译质量错误
        bleu = evaluation.get("bleu_score")
        if bleu is not None:
            errors["translation"] = 1 - bleu if bleu < self.thresholds["bleu"] else 0
        
        return errors
    
    def suggest_adjustments(self, errors: Dict[str, float]) -> Dict[str, Any]:
        """
        根据错误类型建议参数调整
        
        Returns:
            建议的参数调整
        """
        adjustments = {}
        
        # 碎片化过高 → 增加合并阈值
        if errors.get("fragmentation", 0) > 0:
            param = self.adjustable_params["merge_threshold"]
            new_value = min(param["current"] + param["step"], param["max"])
            adjustments["merge_threshold"] = {
                "current": param["current"],
                "suggested": new_value,
                "reason": "碎片化过高，增加合并阈值"
            }
        
        # 时间戳误差过大 → 调整 VAD 阈值
        if errors.get("timestamp", 0) > 0:
            param = self.adjustable_params["vad_threshold"]
            new_value = max(param["current"] - param["step"], param["min"])
            adjustments["vad_threshold"] = {
                "current": param["current"],
                "suggested": new_value,
                "reason": "时间戳误差过大，降低 VAD 阈值"
            }
        
        # 连贯性不足 → 增加翻译批次大小（更多上下文）
        if errors.get("coherence", 0) > 0:
            param = self.adjustable_params["translation_batch_size"]
            new_value = min(param["current"] + param["step"], param["max"])
            adjustments["translation_batch_size"] = {
                "current": param["current"],
                "suggested": new_value,
                "reason": "连贯性不足，增加翻译上下文窗口"
            }
        
        # 翻译质量不佳 → 减小段落长度（更精确翻译）
        if errors.get("translation", 0) > 0:
            param = self.adjustable_params["max_segment_chars"]
            new_value = max(param["current"] - param["step"], param["min"])
            adjustments["max_segment_chars"] = {
                "current": param["current"],
                "suggested": new_value,
                "reason": "翻译质量不佳，减小段落长度"
            }
        
        return adjustments
    
    def apply_adjustments(self, adjustments: Dict[str, Any]):
        """应用参数调整"""
        for param_name, adjustment in adjustments.items():
            if param_name in self.adjustable_params:
                self.adjustable_params[param_name]["current"] = adjustment["suggested"]
                print(f"调整 {param_name}: {adjustment['current']} -> {adjustment['suggested']}")
    
    def run_iteration(self, original_segments: List[Dict], 
                      translated_segments: List[Dict],
                      aligned_segments: List[Dict] = None,
                      reference: List[str] = None) -> Dict[str, Any]:
        """
        运行一次迭代优化
        
        Returns:
            {
                "evaluation": 评估结果,
                "errors": 错误分析,
                "adjustments": 建议调整,
                "improved": 是否有改进
            }
        """
        # 评估
        evaluation = self.evaluator.evaluate(
            original_segments, translated_segments, 
            aligned_segments, reference
        )
        
        # 分析错误
        errors = self.analyze_errors(evaluation)
        
        # 建议调整
        adjustments = self.suggest_adjustments(errors)
        
        # 记录历史
        self.history.append({
            "evaluation": evaluation,
            "errors": errors,
            "adjustments": adjustments
        })
        
        # 检查是否有改进
        improved = False
        if len(self.history) > 1:
            prev_score = self.history[-2]["evaluation"]["overall_score"]
            curr_score = evaluation["overall_score"]
            improved = curr_score > prev_score
        
        return {
            "evaluation": evaluation,
            "errors": errors,
            "adjustments": adjustments,
            "improved": improved
        }
    
    def get_current_params(self) -> Dict[str, float]:
        """获取当前参数值"""
        return {k: v["current"] for k, v in self.adjustable_params.items()}
    
    def reset(self):
        """重置到默认参数"""
        defaults = {
            "merge_threshold": 1.0,
            "max_segment_chars": 120,
            "translation_batch_size": 10,
            "vad_threshold": 0.5
        }
        for k, v in defaults.items():
            if k in self.adjustable_params:
                self.adjustable_params[k]["current"] = v
        self.history = []


class AdvancedProcessor:
    """
    高级处理器 - 整合所有功能
    
    使用示例:
        processor = AdvancedProcessor()
        result = processor.process(segments, target_lang="zh")
    """
    
    def __init__(self, terminology_file: str = None):
        self.analyzer = ContentAnalyzer()
        self.segmenter = AdaptiveSegmenter()
        self.evaluator = QualityEvaluator()
        self.terminology = TerminologyManager(terminology_file)
        self.feedback = FeedbackLoop()
    
    def process(self, segments: List[Dict], target_lang: str = "zh",
                auto_optimize: bool = True, max_iterations: int = 3,
                translator_func = None) -> Dict[str, Any]:
        """
        高级处理流程
        
        Args:
            segments: 原始 ASR 段落
            target_lang: 目标语言
            auto_optimize: 是否自动迭代优化
            max_iterations: 最大迭代次数
            translator_func: 翻译函数 (texts) -> translated_texts
            
        Returns:
            {
                "content_analysis": 内容分析结果,
                "processed_segments": 处理后的段落,
                "translated_segments": 翻译后的段落,
                "evaluation": 质量评估,
                "terminology": 提取的术语,
                "iterations": 迭代次数
            }
        """
        result = {
            "content_analysis": None,
            "processed_segments": [],
            "translated_segments": [],
            "evaluation": None,
            "terminology": [],
            "iterations": 0
        }
        
        # 1. 内容类型分析
        print("分析内容类型...")
        analysis = self.analyzer.analyze(segments)
        result["content_analysis"] = analysis
        print(f"  类型: {analysis['content_type']} (置信度: {analysis['confidence']})")
        
        # 2. 提取术语
        if analysis["content_type"] == ContentType.TECHNICAL:
            print("提取技术术语...")
            terms = self.terminology.extract_and_add(segments, self.analyzer)
            result["terminology"] = terms
        
        # 3. 自适应分段
        print(f"应用 {analysis['content_type']} 分段策略...")
        processed = self.segmenter.segment(
            segments, 
            analysis["content_type"],
            analysis.get("detected_terms", [])
        )
        result["processed_segments"] = processed
        print(f"  分段: {len(segments)} -> {len(processed)}")
        
        # 4. 翻译（如果提供了翻译函数）
        if translator_func:
            print("执行翻译...")
            texts = [seg.get("text", "") for seg in processed]
            translated_texts = translator_func(texts)
            
            # 应用术语表
            if analysis["content_type"] == ContentType.TECHNICAL:
                translated_texts = [
                    self.terminology.apply_to_text(t) for t in translated_texts
                ]
            
            # 构建翻译后的段落
            translated_segments = []
            for seg, trans_text in zip(processed, translated_texts):
                new_seg = seg.copy()
                new_seg["text"] = trans_text
                new_seg["original_text"] = seg.get("text", "")
                translated_segments.append(new_seg)
            
            result["translated_segments"] = translated_segments
            
            # 5. 质量评估
            print("评估质量...")
            evaluation = self.evaluator.evaluate(
                processed, translated_segments
            )
            result["evaluation"] = evaluation
            print(f"  综合得分: {evaluation['overall_score']}")
            
            # 6. 迭代优化
            if auto_optimize and evaluation["overall_score"] < 0.8:
                print("启动迭代优化...")
                
                for i in range(max_iterations):
                    iteration = self.feedback.run_iteration(
                        processed, translated_segments
                    )
                    result["iterations"] = i + 1
                    
                    if not iteration["adjustments"]:
                        print(f"  迭代 {i+1}: 无需调整")
                        break
                    
                    print(f"  迭代 {i+1}: 建议调整 {list(iteration['adjustments'].keys())}")
                    
                    # 应用调整
                    self.feedback.apply_adjustments(iteration["adjustments"])
                    
                    # 重新处理
                    params = self.feedback.get_current_params()
                    
                    # 更新分段策略参数
                    strategy = self.segmenter.strategies.get(
                        analysis["content_type"], 
                        self.segmenter.strategies[ContentType.MIXED]
                    )
                    strategy["max_chars"] = int(params["max_segment_chars"])
                    strategy["min_duration"] = params["merge_threshold"]
                    
                    # 重新分段
                    processed = self.segmenter.segment(
                        segments, analysis["content_type"],
                        analysis.get("detected_terms", [])
                    )
                    
                    # 重新翻译
                    texts = [seg.get("text", "") for seg in processed]
                    translated_texts = translator_func(texts)
                    
                    translated_segments = []
                    for seg, trans_text in zip(processed, translated_texts):
                        new_seg = seg.copy()
                        new_seg["text"] = trans_text
                        translated_segments.append(new_seg)
                    
                    # 重新评估
                    evaluation = self.evaluator.evaluate(processed, translated_segments)
                    
                    if iteration["improved"]:
                        print(f"  得分提升: {evaluation['overall_score']}")
                        result["processed_segments"] = processed
                        result["translated_segments"] = translated_segments
                        result["evaluation"] = evaluation
                    else:
                        print(f"  未改进，停止迭代")
                        break
        
        return result
    
    def get_processing_report(self, result: Dict) -> str:
        """生成处理报告"""
        report = []
        report.append("=" * 50)
        report.append("高级处理报告")
        report.append("=" * 50)
        
        # 内容分析
        if result.get("content_analysis"):
            analysis = result["content_analysis"]
            report.append(f"\n内容类型: {analysis['content_type']}")
            report.append(f"置信度: {analysis['confidence']}")
            report.append(f"类型得分: {analysis['scores']}")
            if analysis.get("detected_terms"):
                report.append(f"检测到术语: {len(analysis['detected_terms'])} 个")
        
        # 分段信息
        report.append(f"\n处理后段落数: {len(result.get('processed_segments', []))}")
        report.append(f"翻译后段落数: {len(result.get('translated_segments', []))}")
        
        # 质量评估
        if result.get("evaluation"):
            eval_result = result["evaluation"]
            report.append(f"\n质量评估:")
            report.append(f"  综合得分: {eval_result['overall_score']}")
            if eval_result.get("bleu_score") is not None:
                report.append(f"  BLEU 分数: {eval_result['bleu_score']}")
            report.append(f"  时间戳误差: {eval_result['timestamp_error']}s")
            report.append(f"  连贯性得分: {eval_result['coherence_score']}")
            report.append(f"  碎片化程度: {eval_result['fragmentation_score']}")
        
        # 迭代信息
        if result.get("iterations", 0) > 0:
            report.append(f"\n迭代优化次数: {result['iterations']}")
        
        report.append("\n" + "=" * 50)
        
        return "\n".join(report)


# 便捷函数
def analyze_content(segments: List[Dict]) -> Dict:
    """分析内容类型"""
    analyzer = ContentAnalyzer()
    return analyzer.analyze(segments)


def evaluate_quality(original: List[Dict], translated: List[Dict],
                    reference: List[str] = None) -> Dict:
    """评估翻译质量"""
    evaluator = QualityEvaluator()
    return evaluator.evaluate(original, translated, reference_translation=reference)


if __name__ == "__main__":
    print("高级处理模块")
    print("=" * 50)
    print("""
功能:
1. ContentAnalyzer - 内容类型分析（对话/演讲/技术）
2. AdaptiveSegmenter - 自适应分段策略
3. QualityEvaluator - 质量评估（BLEU/时间戳/连贯性）
4. TerminologyManager - 术语表管理
5. FeedbackLoop - 迭代优化反馈循环
6. AdvancedProcessor - 整合所有功能

使用示例:
    from video_tool.core.advanced_processor import AdvancedProcessor
    
    processor = AdvancedProcessor()
    result = processor.process(
        segments,
        target_lang="zh",
        auto_optimize=True,
        translator_func=my_translate_function
    )
    
    print(processor.get_processing_report(result))
    """)
