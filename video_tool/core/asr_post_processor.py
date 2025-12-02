"""
ASR 后处理优化模块

功能：
1. 修复常见 ASR 错误
2. 智能句子合并（基于语义完整性）
3. 标点修复
4. 专有名词修正
5. 上下文感知合并
6. 外部词库支持

使用：
    from video_tool.core.asr_post_processor import ASRPostProcessor
    
    processor = ASRPostProcessor()
    optimized = processor.optimize(segments)
    
    # 使用外部词库
    processor = ASRPostProcessor(use_external_dict=True)
    optimized = processor.optimize(segments)
"""

import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

# 尝试导入词库管理器
try:
    from video_tool.core.dictionary_manager import (
        DictionaryManager, 
        get_dictionary_manager,
        correct_text as dict_correct_text
    )
    DICT_MANAGER_AVAILABLE = True
except ImportError:
    DICT_MANAGER_AVAILABLE = False


@dataclass
class Segment:
    """字幕段落"""
    start: float
    end: float
    text: str
    words: List[Dict] = field(default_factory=list)
    
    @property
    def duration(self) -> float:
        return self.end - self.start
    
    @property
    def word_count(self) -> int:
        return len(self.text.split())
    
    def to_dict(self) -> Dict:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "words": self.words
        }


class ASRPostProcessor:
    """ASR 后处理优化器"""
    
    # 常见 ASR 错误修复映射
    COMMON_FIXES = {
        # Faster-Whisper 常见错误
        "Trick-lifr's": "trickle",
        "trick-lifr's": "trickle",
        "Trick lifr's": "trickle",
        "trickle of of": "trickle of",  # 修复重复
        "mAIn": "main",
        "mAin": "main",
        "MAIn": "main",
        "obtAIning": "obtaining",
        "obtAining": "obtaining",
        "progRAMs": "programs",
        "progRams": "programs",
        "avAIlable": "available",
        "avAilable": "available",
        "commUnity": "community",
        "commUnIty": "community",
        "Gado": "Godot",
        "intagers": "integers",
        "th.": "this",
        "cts": "acts",
        
        # 常见短语错误
        "see the light day": "see the light of day",
        "light day": "light of day",
        "kind of a": "kind of",
        "sort of a": "sort of",
        "a lot of of": "a lot of",
        "going to to": "going to",
        "Wayland stuff, which I covered in a previous?": "Wayland stuff, which I covered in a previous video?",
        
        # Godot 相关术语
        "F keys": "FKeys",
        "on ready": "onready",
        "on-readies": "onreadies",
        "on ready variable": "onready variable",
        "drag and drop export variable": "drag-and-drop export variable",
        "export references": "exported references",
        "cubal games.com": "cubalgames.com",
        
        # 技术术语大写
        "prs": "PRs",
        " pr ": " PR ",
        " pr.": " PR.",
        " pr,": " PR,",
        "github": "GitHub",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "python": "Python",
        "godot": "Godot",
        "unity": "Unity",
        "unreal": "Unreal",
        "api": "API",
        "apis": "APIs",
        "sdk": "SDK",
        "http": "HTTP",
        "https": "HTTPS",
        "json": "JSON",
        "xml": "XML",
        "html": "HTML",
        "css": "CSS",
        "sql": "SQL",
        "cpu": "CPU",
        "gpu": "GPU",
        "ram": "RAM",
        "ssd": "SSD",
        "ai": "AI",
        "ml": "ML",
        "llm": "LLM",
        "gpt": "GPT",
        "npm": "npm",
        "vs code": "VS Code",
        "VS code": "VS Code",
        "xr": "XR",
        "qol": "quality of life",
        "QOL": "quality of life",
        # "dev" 不修改，因为在版本号中应保持原样（如 4.6 Dev1）
    }
    
    # 正则表达式修正模式
    REGEX_FIXES = [
        # 修复 Dev 后面的空格问题: Dev 1 -> Dev1
        (r'\bDev\s+(\d+)', r'Dev\1'),
        # 确保 PR/PRs 大写
        (r'\bPRs?\b', lambda m: m.group(0).upper()),
        # 确保 XR 大写
        (r'\bXR\b', 'XR'),
        # 修复混合大小写的常见错误
        (r'\bmAIn\b', 'main'),
        (r'\bmAin\b', 'main'),
        (r'\bMAIn\b', 'main'),
        (r'\bobtAIning\b', 'obtaining'),
        (r'\bobtAining\b', 'obtaining'),
        (r'\bprogRAMs\b', 'programs'),
        (r'\bprogRams\b', 'programs'),
        (r'\bavAIlable\b', 'available'),
        (r'\bavAilable\b', 'available'),
        (r'\bcommUnity\b', 'community'),
        (r'\bcommUnIty\b', 'community'),
    ]
    
    # 句子结束标点
    SENTENCE_ENDINGS = ('.', '!', '?', '。', '！', '？')
    
    # 需要合并的连接词（句末）
    CONTINUATION_ENDINGS = (
        ',', ';', ':', ' -',
        ' but', ' and', ' or', ' so', ' because', ' though',
        ' which', ' that', ' who', ' where', ' when',
        ' as', ' if', ' while', ' although', ' unless',
        ' however', ' therefore', ' moreover', ' furthermore',
    )
    
    # 疑问词
    QUESTION_WORDS = ('who', 'what', 'where', 'when', 'why', 'how', 'which', 'whose')
    
    def __init__(self, 
                 min_segment_duration: float = 1.5,
                 max_segment_duration: float = 8.0,  # 降低到 8 秒
                 min_words: int = 4,
                 max_words: int = 20,  # 降低到 20 词
                 merge_gap_threshold: float = 0.3,  # 降低间隔阈值
                 use_external_dict: bool = True):  # 使用外部词库
        """
        初始化后处理器
        
        Args:
            min_segment_duration: 最小段落时长（秒）
            max_segment_duration: 最大段落时长（秒）
            min_words: 最小词数
            max_words: 最大词数
            merge_gap_threshold: 合并间隔阈值（秒）
            use_external_dict: 是否使用外部词库
        """
        self.min_segment_duration = min_segment_duration
        self.use_external_dict = use_external_dict and DICT_MANAGER_AVAILABLE
        self.dict_manager = None
        
        # 如果启用外部词库，初始化词库管理器
        if self.use_external_dict:
            try:
                self.dict_manager = get_dictionary_manager()
            except Exception as e:
                print(f"警告: 无法加载外部词库: {e}")
                self.use_external_dict = False
        self.max_segment_duration = max_segment_duration
        self.min_words = min_words
        self.max_words = max_words
        self.merge_gap_threshold = merge_gap_threshold
    
    def optimize(self, segments: List[Dict]) -> List[Dict]:
        """
        完整优化流程
        
        Args:
            segments: 原始段落列表 [{"start": float, "end": float, "text": str}, ...]
            
        Returns:
            优化后的段落列表
        """
        if not segments:
            return segments
        
        # 转换为 Segment 对象
        segs = [Segment(
            start=s.get("start", 0),
            end=s.get("end", 0),
            text=s.get("text", "").strip(),
            words=s.get("words", [])
        ) for s in segments]
        
        # 步骤 1: 修复标点（先修复标点，便于后续判断）
        segs = self._fix_punctuation(segs)
        
        # 步骤 2: 智能合并（先合并，再修复错误）
        segs = self._smart_merge(segs)
        
        # 步骤 3: 修复常见错误（合并后再修复，可以处理跨段落的错误）
        segs = self._fix_common_errors(segs)
        
        # 步骤 4: 确保句子完整性
        segs = self._ensure_sentence_completeness(segs)
        
        # 步骤 5: 最终清理
        segs = self._final_cleanup(segs)
        
        # 转换回字典
        return [s.to_dict() for s in segs]
    
    def _fix_common_errors(self, segments: List[Segment]) -> List[Segment]:
        """修复常见 ASR 错误"""
        for seg in segments:
            text = seg.text
            
            # 优先使用外部词库
            if self.use_external_dict and self.dict_manager:
                text = self.dict_manager.correct_text(text)
            else:
                # 回退到内置修复映射
                for wrong, correct in self.COMMON_FIXES.items():
                    # 使用不区分大小写的替换
                    pattern = re.compile(re.escape(wrong), re.IGNORECASE)
                    text = pattern.sub(correct, text)
            
            # 应用正则表达式修正（始终应用）
            for pattern, replacement in self.REGEX_FIXES:
                if callable(replacement):
                    text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                else:
                    text = re.sub(pattern, replacement, text)
            
            seg.text = text
        
        return segments
    
    def _fix_punctuation(self, segments: List[Segment]) -> List[Segment]:
        """修复标点问题"""
        for seg in segments:
            text = seg.text
            
            # 移除标点前的多余空格
            text = re.sub(r'\s+([.,!?;:\'"])', r'\1', text)
            
            # 确保句号后有空格（如果后面是大写字母）
            text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
            
            # 修复多余的空格
            text = ' '.join(text.split())
            
            # 修复引号
            text = text.replace('``', '"').replace("''", '"')
            
            seg.text = text
        
        return segments

    
    def _smart_merge(self, segments: List[Segment]) -> List[Segment]:
        """
        智能合并段落
        
        合并规则：
        1. 当前段以小写字母开头（可能是上一句的继续）
        2. 当前段以连接词/逗号结尾
        3. 下一段很短且间隔很小
        4. 当前段不是完整句子
        """
        if len(segments) < 2:
            return segments
        
        merged = []
        i = 0
        
        while i < len(segments):
            current = segments[i]
            
            # 检查是否需要与后续段落合并
            segments_to_merge = [current]
            
            # 计算已合并的总时长和词数
            total_duration = current.duration
            total_words = current.word_count
            
            while i + len(segments_to_merge) < len(segments):
                next_seg = segments[i + len(segments_to_merge)]
                
                # 先检查合并后是否会超限（使用累计值）
                new_duration = next_seg.end - segments_to_merge[0].start
                new_words = total_words + next_seg.word_count
                
                # 严格限制：超过限制就不合并
                if new_duration > self.max_segment_duration:
                    break
                if new_words > self.max_words:
                    break
                
                # 检查是否应该合并
                should_merge = self._should_merge(
                    segments_to_merge[-1], 
                    next_seg,
                    len(segments_to_merge),
                    new_duration,
                    new_words
                )
                
                if should_merge:
                    segments_to_merge.append(next_seg)
                    total_duration = new_duration
                    total_words = new_words
                else:
                    break
            
            # 执行合并
            if len(segments_to_merge) > 1:
                merged_seg = self._merge_segments(segments_to_merge)
                merged.append(merged_seg)
            else:
                merged.append(current)
            
            i += len(segments_to_merge)
        
        return merged
    
    def _should_merge(self, current: Segment, next_seg: Segment, 
                      merge_count: int, total_duration: float = None,
                      total_words: int = None) -> bool:
        """
        判断是否应该合并两个段落
        
        基于语义的智能判断规则：
        1. 下一段以小写开头（很可能是前一句的延续）
        2. 当前段以连接词或逗号结尾
        3. 当前段以不完整的短语结束
        4. 时间间隔很短
        5. 当前段太短
        """
        # 检查间隔 - 间隔太大不合并
        gap = next_seg.start - current.end
        if gap > self.merge_gap_threshold * (merge_count + 1):
            return False
        
        # 如果已经合并了很多段，更保守
        if merge_count >= 3:
            # 只有非常短的段落才继续合并
            if next_seg.word_count >= self.min_words and next_seg.duration >= self.min_segment_duration:
                return False
        
        current_text = current.text.strip()
        next_text = next_seg.text.strip()
        
        # 如果当前段已经是完整句子（以句号结尾），不再合并
        if current_text.endswith(self.SENTENCE_ENDINGS):
            # 除非下一段以小写开头（可能是错误分割）
            if next_text and next_text[0].isupper():
                return False
        
        # 规则 1: 下一段以小写字母开头（可能是句子的继续）
        if next_text and next_text[0].islower():
            return True
        
        # 规则 2: 当前段以连接词/逗号结尾
        for ending in self.CONTINUATION_ENDINGS:
            if current_text.lower().endswith(ending.lower()):
                return True
        
        # 规则 3: 当前段以不完整的短语结束（词数太少且无句号）
        current_words = current_text.split()
        if len(current_words) < self.min_words and not current_text.endswith(self.SENTENCE_ENDINGS):
            return True
        
        # 规则 4: 时间间隔很短（< 0.3秒）
        if gap < 0.3:
            # 如果间隔很短且当前段不是完整句子
            if not current_text.endswith(self.SENTENCE_ENDINGS):
                return True
        
        # 规则 5: 当前段不是完整句子且下一段很短
        if not current_text.endswith(self.SENTENCE_ENDINGS):
            if next_seg.word_count < self.min_words:
                return True
            if next_seg.duration < self.min_segment_duration:
                return True
        
        # 规则 6: 当前段太短
        if current.word_count < self.min_words or current.duration < self.min_segment_duration:
            return True
        
        # 规则 7: 检查是否以介词/冠词/连词结尾（不完整句子）
        incomplete_endings = ('to', 'of', 'for', 'with', 'in', 'on', 'at', 'by', 'from',
                              'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be',
                              'can', 'could', 'will', 'would', 'shall', 'should')
        last_word = current_words[-1].lower().rstrip('.,;:') if current_words else ''
        if last_word in incomplete_endings:
            return True
        
        return False
    
    def _merge_segments(self, segments: List[Segment]) -> Segment:
        """合并多个段落"""
        if not segments:
            return None
        
        if len(segments) == 1:
            return segments[0]
        
        # 合并文本
        texts = []
        for seg in segments:
            text = seg.text.strip()
            # 移除末尾的不完整标点
            if text and text[-1] in (',', ';', ':'):
                text = text[:-1]
            texts.append(text)
        
        merged_text = ' '.join(texts)
        
        # 合并词级时间戳
        merged_words = []
        for seg in segments:
            merged_words.extend(seg.words)
        
        return Segment(
            start=segments[0].start,
            end=segments[-1].end,
            text=merged_text,
            words=merged_words
        )
    
    def _ensure_sentence_completeness(self, segments: List[Segment]) -> List[Segment]:
        """确保句子完整性"""
        for seg in segments:
            text = seg.text.strip()
            
            if not text:
                continue
            
            # 如果不以句子结束标点结尾
            if not text.endswith(self.SENTENCE_ENDINGS):
                # 判断是否是问句
                text_lower = text.lower()
                is_question = any(
                    text_lower.startswith(qw) or f' {qw} ' in text_lower
                    for qw in self.QUESTION_WORDS
                )
                
                if is_question:
                    text = text.rstrip('.,;:') + '?'
                else:
                    text = text.rstrip('.,;:') + '.'
            
            seg.text = text
        
        return segments
    
    def _final_cleanup(self, segments: List[Segment]) -> List[Segment]:
        """最终清理和格式化"""
        cleaned = []
        
        for seg in segments:
            text = seg.text.strip()
            
            if not text:
                continue
            
            # 移除多余空格
            text = ' '.join(text.split())
            
            # 修复标点前的空格
            text = re.sub(r'\s+([.,!?;:])', r'\1', text)
            
            # 确保标点后有空格（如果后面是字母）
            text = re.sub(r'([.,!?;:])(?=[A-Za-z])', r'\1 ', text)
            
            # 修复重复的标点
            text = re.sub(r'([.,!?])\1+', r'\1', text)
            
            # 修复引号
            text = text.replace('``', '"').replace("''", '"')
            
            # 确保句首大写
            if text and text[0].isalpha():
                text = text[0].upper() + text[1:]
            
            seg.text = text
            cleaned.append(seg)
        
        return cleaned


class ContextAwareMerger:
    """
    上下文感知合并器
    
    专门处理被不合理拆分的句子
    """
    
    def __init__(self):
        # 不完整句子的模式
        self.incomplete_patterns = [
            # 以介词结尾
            r'\b(to|of|for|with|in|on|at|by|from|about|into|through|during|before|after|above|below|between|under|over)\s*$',
            # 以冠词结尾
            r'\b(a|an|the)\s*$',
            # 以连词结尾
            r'\b(and|or|but|so|because|although|though|while|if|when|where|which|that|who)\s*$',
            # 以动词 be 结尾
            r'\b(is|are|was|were|be|been|being)\s*$',
            # 以情态动词结尾
            r'\b(can|could|will|would|shall|should|may|might|must)\s*$',
            # 以 "to" + 动词原形 的 "to" 结尾
            r'\bto\s*$',
        ]
        
        self.incomplete_regex = [re.compile(p, re.IGNORECASE) for p in self.incomplete_patterns]
    
    def merge(self, segments: List[Dict]) -> List[Dict]:
        """
        基于上下文的智能合并
        """
        if len(segments) < 2:
            return segments
        
        merged = []
        i = 0
        
        while i < len(segments):
            current = segments[i].copy()
            
            # 检查当前段是否不完整
            while i < len(segments) - 1 and self._is_incomplete(current['text']):
                next_seg = segments[i + 1]
                
                # 合并
                current['text'] = current['text'].strip() + ' ' + next_seg['text'].strip()
                current['end'] = next_seg['end']
                
                if 'words' in current and 'words' in next_seg:
                    current['words'] = current.get('words', []) + next_seg.get('words', [])
                
                i += 1
            
            merged.append(current)
            i += 1
        
        return merged
    
    def _is_incomplete(self, text: str) -> bool:
        """检查文本是否不完整"""
        text = text.strip()
        
        if not text:
            return False
        
        # 如果以句子结束标点结尾，认为是完整的
        if text[-1] in '.!?。！？':
            return False
        
        # 检查不完整模式
        for pattern in self.incomplete_regex:
            if pattern.search(text):
                return True
        
        return False


class TechnicalTermCorrector:
    """
    技术术语修正器
    
    自动识别和修正技术术语的大小写
    """
    
    # 技术术语词典
    TECH_TERMS = {
        # 编程语言
        'javascript': 'JavaScript',
        'typescript': 'TypeScript',
        'python': 'Python',
        'java': 'Java',
        'kotlin': 'Kotlin',
        'swift': 'Swift',
        'rust': 'Rust',
        'golang': 'Golang',
        'csharp': 'C#',
        'cpp': 'C++',
        
        # 游戏引擎
        'godot': 'Godot',
        'unity': 'Unity',
        'unreal': 'Unreal',
        
        # 框架和工具
        'react': 'React',
        'vue': 'Vue',
        'angular': 'Angular',
        'nodejs': 'Node.js',
        'nextjs': 'Next.js',
        'django': 'Django',
        'flask': 'Flask',
        'fastapi': 'FastAPI',
        'pytorch': 'PyTorch',
        'tensorflow': 'TensorFlow',
        
        # 平台和服务
        'github': 'GitHub',
        'gitlab': 'GitLab',
        'bitbucket': 'Bitbucket',
        'docker': 'Docker',
        'kubernetes': 'Kubernetes',
        'aws': 'AWS',
        'azure': 'Azure',
        'gcp': 'GCP',
        
        # 缩写
        'api': 'API',
        'apis': 'APIs',
        'sdk': 'SDK',
        'sdks': 'SDKs',
        'http': 'HTTP',
        'https': 'HTTPS',
        'json': 'JSON',
        'xml': 'XML',
        'html': 'HTML',
        'css': 'CSS',
        'sql': 'SQL',
        'nosql': 'NoSQL',
        'cpu': 'CPU',
        'gpu': 'GPU',
        'ram': 'RAM',
        'ssd': 'SSD',
        'hdd': 'HDD',
        'ai': 'AI',
        'ml': 'ML',
        'llm': 'LLM',
        'nlp': 'NLP',
        'gpt': 'GPT',
        'pr': 'PR',
        'prs': 'PRs',
        'ci': 'CI',
        'cd': 'CD',
        'ui': 'UI',
        'ux': 'UX',
        'ide': 'IDE',
        'cli': 'CLI',
        'gui': 'GUI',
        'url': 'URL',
        'uri': 'URI',
        'ip': 'IP',
        'tcp': 'TCP',
        'udp': 'UDP',
        'dns': 'DNS',
        'ssl': 'SSL',
        'tls': 'TLS',
        'ssh': 'SSH',
        'ftp': 'FTP',
        'npm': 'npm',
        'pip': 'pip',
        'git': 'Git',
    }
    
    def __init__(self, custom_terms: Dict[str, str] = None):
        """
        初始化
        
        Args:
            custom_terms: 自定义术语映射
        """
        self.terms = self.TECH_TERMS.copy()
        if custom_terms:
            self.terms.update(custom_terms)
        
        # 构建正则表达式
        self._build_patterns()
    
    def _build_patterns(self):
        """构建匹配模式"""
        self.patterns = {}
        for term_lower, term_correct in self.terms.items():
            # 使用词边界匹配
            pattern = re.compile(r'\b' + re.escape(term_lower) + r'\b', re.IGNORECASE)
            self.patterns[pattern] = term_correct
    
    def correct(self, text: str) -> str:
        """修正文本中的技术术语"""
        for pattern, correct in self.patterns.items():
            text = pattern.sub(correct, text)
        return text
    
    def correct_segments(self, segments: List[Dict]) -> List[Dict]:
        """修正段落列表中的技术术语"""
        for seg in segments:
            if 'text' in seg:
                seg['text'] = self.correct(seg['text'])
        return segments
    
    def add_term(self, term_lower: str, term_correct: str):
        """添加自定义术语"""
        self.terms[term_lower.lower()] = term_correct
        pattern = re.compile(r'\b' + re.escape(term_lower) + r'\b', re.IGNORECASE)
        self.patterns[pattern] = term_correct


def optimize_asr_output(segments: List[Dict], 
                        min_duration: float = 1.5,
                        max_duration: float = 8.0,
                        min_words: int = 4,
                        max_words: int = 20,
                        custom_terms: Dict[str, str] = None) -> List[Dict]:
    """
    优化 ASR 输出的便捷函数
    
    Args:
        segments: 原始段落列表
        min_duration: 最小段落时长
        max_duration: 最大段落时长
        min_words: 最小词数
        max_words: 最大词数
        custom_terms: 自定义术语映射
        
    Returns:
        优化后的段落列表
    """
    # 1. 技术术语修正
    term_corrector = TechnicalTermCorrector(custom_terms)
    segments = term_corrector.correct_segments(segments)
    
    # 2. 上下文感知合并
    context_merger = ContextAwareMerger()
    segments = context_merger.merge(segments)
    
    # 3. 完整后处理
    processor = ASRPostProcessor(
        min_segment_duration=min_duration,
        max_segment_duration=max_duration,
        min_words=min_words,
        max_words=max_words
    )
    segments = processor.optimize(segments)
    
    return segments





class ASRQualityMonitor:
    """
    ASR 质量实时监控器
    
    监控指标：
    - 平均词数/段
    - 完整句子比例
    - 平均时长
    - 错误检测
    - 质量评分
    """
    
    # 常见 ASR 错误模式
    ERROR_PATTERNS = [
        "see the light day",
        "prs ",
        " pr ",
        "kind of a",
        "sort of a",
        "a lot of of",
        "going to to",
    ]
    
    # 理想指标范围
    IDEAL_METRICS = {
        "avg_words_per_segment": (8, 15),      # 理想词数范围
        "avg_duration": (2.0, 6.0),            # 理想时长范围（秒）
        "complete_sentence_ratio": (0.7, 1.0), # 完整句子比例
        "error_ratio": (0.0, 0.05),            # 错误比例
    }
    
    def __init__(self):
        self.history = []
    
    def monitor(self, segments: List[Dict]) -> Dict:
        """
        监控 ASR 质量指标
        
        Args:
            segments: 字幕段落列表
            
        Returns:
            质量指标字典
        """
        if not segments:
            return self._empty_metrics()
        
        total = len(segments)
        
        # 计算各项指标
        word_counts = []
        durations = []
        complete_sentences = 0
        segments_with_errors = 0
        
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
            
            # 完整句子
            if text and text[-1] in '.!?。！？':
                complete_sentences += 1
            
            # 错误检测
            text_lower = text.lower()
            if any(err in text_lower for err in self.ERROR_PATTERNS):
                segments_with_errors += 1
        
        # 计算指标
        avg_words = sum(word_counts) / total
        avg_duration = sum(durations) / total
        complete_ratio = complete_sentences / total
        error_ratio = segments_with_errors / total
        
        metrics = {
            "total_segments": total,
            "avg_words_per_segment": round(avg_words, 2),
            "avg_duration": round(avg_duration, 2),
            "complete_sentences": complete_sentences,
            "complete_sentence_ratio": round(complete_ratio, 3),
            "segments_with_errors": segments_with_errors,
            "error_ratio": round(error_ratio, 3),
            "word_count_std": round(self._std(word_counts), 2),
            "duration_std": round(self._std(durations), 2),
        }
        
        # 计算质量评分
        metrics["quality_score"] = self._calculate_quality_score(metrics)
        metrics["quality_grade"] = self._get_quality_grade(metrics["quality_score"])
        metrics["suggestions"] = self._get_suggestions(metrics)
        
        # 记录历史
        self.history.append(metrics)
        
        return metrics
    
    def _empty_metrics(self) -> Dict:
        """返回空指标"""
        return {
            "total_segments": 0,
            "avg_words_per_segment": 0,
            "avg_duration": 0,
            "complete_sentences": 0,
            "complete_sentence_ratio": 0,
            "segments_with_errors": 0,
            "error_ratio": 0,
            "quality_score": 0,
            "quality_grade": "N/A",
            "suggestions": []
        }
    
    def _std(self, values: List[float]) -> float:
        """计算标准差"""
        if not values:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5
    
    def _calculate_quality_score(self, metrics: Dict) -> float:
        """
        计算综合质量评分 (0-100)
        """
        score = 100.0
        
        # 词数评分
        avg_words = metrics["avg_words_per_segment"]
        ideal_min, ideal_max = self.IDEAL_METRICS["avg_words_per_segment"]
        if avg_words < ideal_min:
            score -= (ideal_min - avg_words) * 3
        elif avg_words > ideal_max:
            score -= (avg_words - ideal_max) * 2
        
        # 时长评分
        avg_duration = metrics["avg_duration"]
        ideal_min, ideal_max = self.IDEAL_METRICS["avg_duration"]
        if avg_duration < ideal_min:
            score -= (ideal_min - avg_duration) * 5
        elif avg_duration > ideal_max:
            score -= (avg_duration - ideal_max) * 3
        
        # 完整句子评分
        complete_ratio = metrics["complete_sentence_ratio"]
        ideal_min, _ = self.IDEAL_METRICS["complete_sentence_ratio"]
        if complete_ratio < ideal_min:
            score -= (ideal_min - complete_ratio) * 30
        
        # 错误评分
        error_ratio = metrics["error_ratio"]
        _, ideal_max = self.IDEAL_METRICS["error_ratio"]
        if error_ratio > ideal_max:
            score -= (error_ratio - ideal_max) * 100
        
        # 标准差惩罚（过大的变异表示不稳定）
        if metrics["word_count_std"] > 5:
            score -= (metrics["word_count_std"] - 5) * 2
        
        return max(0, min(100, round(score, 1)))
    
    def _get_quality_grade(self, score: float) -> str:
        """获取质量等级"""
        if score >= 90:
            return "A (优秀)"
        elif score >= 80:
            return "B (良好)"
        elif score >= 70:
            return "C (一般)"
        elif score >= 60:
            return "D (较差)"
        else:
            return "F (需改进)"
    
    def _get_suggestions(self, metrics: Dict) -> List[str]:
        """根据指标生成优化建议"""
        suggestions = []
        
        # 词数建议
        avg_words = metrics["avg_words_per_segment"]
        if avg_words < 5:
            suggestions.append("段落过短，建议增加 VAD min_silence_duration_ms 参数")
        elif avg_words > 20:
            suggestions.append("段落过长，建议减少 VAD min_silence_duration_ms 参数")
        
        # 时长建议
        avg_duration = metrics["avg_duration"]
        if avg_duration < 1.5:
            suggestions.append("时长过短，建议调整 VAD 参数减少过度分段")
        elif avg_duration > 8:
            suggestions.append("时长过长，建议启用后处理分段")
        
        # 完整句子建议
        if metrics["complete_sentence_ratio"] < 0.6:
            suggestions.append("完整句子比例低，建议启用智能合并后处理")
        
        # 错误建议
        if metrics["error_ratio"] > 0.05:
            suggestions.append("检测到 ASR 错误，建议启用后处理修复")
        
        # 标准差建议
        if metrics["word_count_std"] > 8:
            suggestions.append("段落长度变化大，建议使用自适应分段")
        
        return suggestions
    
    def get_trend(self) -> Dict:
        """获取质量趋势（基于历史记录）"""
        if len(self.history) < 2:
            return {"trend": "insufficient_data"}
        
        recent = self.history[-5:]  # 最近5次
        scores = [m["quality_score"] for m in recent]
        
        # 计算趋势
        if len(scores) >= 2:
            diff = scores[-1] - scores[0]
            if diff > 5:
                trend = "improving"
            elif diff < -5:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"
        
        return {
            "trend": trend,
            "recent_scores": scores,
            "avg_score": round(sum(scores) / len(scores), 1)
        }
    
    def print_report(self, metrics: Dict):
        """打印质量报告"""
        print("\n" + "=" * 50)
        print("ASR 质量监控报告")
        print("=" * 50)
        print(f"总段落数: {metrics['total_segments']}")
        print(f"平均词数/段: {metrics['avg_words_per_segment']}")
        print(f"平均时长: {metrics['avg_duration']}s")
        print(f"完整句子: {metrics['complete_sentences']} ({metrics['complete_sentence_ratio']*100:.1f}%)")
        print(f"检测到错误: {metrics['segments_with_errors']} ({metrics['error_ratio']*100:.1f}%)")
        print(f"\n质量评分: {metrics['quality_score']}/100 - {metrics['quality_grade']}")
        
        if metrics['suggestions']:
            print("\n优化建议:")
            for i, suggestion in enumerate(metrics['suggestions'], 1):
                print(f"  {i}. {suggestion}")
        
        print("=" * 50 + "\n")


def monitor_asr_quality(segments: List[Dict]) -> Dict:
    """
    监控 ASR 质量的便捷函数
    
    Args:
        segments: 字幕段落列表
        
    Returns:
        质量指标字典
    """
    monitor = ASRQualityMonitor()
    return monitor.monitor(segments)


# ============================================================================
# VAD 后处理和质量评估
# ============================================================================

def should_merge_sentences(text1: str, text2: str) -> bool:
    """
    判断两个句子是否应该合并
    
    基于语义判断：
    1. 第一句以小写结尾或不完整
    2. 第二句以小写开头
    3. 第一句以连接词结尾
    """
    text1 = text1.strip()
    text2 = text2.strip()
    
    if not text1 or not text2:
        return False
    
    # 规则1: 第二句以小写开头
    if text2[0].islower():
        return True
    
    # 规则2: 第一句不以句号结尾
    if not text1.endswith(('.', '!', '?', '。', '！', '？')):
        return True
    
    # 规则3: 第一句以连接词结尾
    continuation_words = ('and', 'or', 'but', 'so', 'because', 'though', 
                          'which', 'that', 'who', 'where', 'when', 'if')
    last_word = text1.rstrip('.,;:!?').split()[-1].lower() if text1.split() else ''
    if last_word in continuation_words:
        return True
    
    # 规则4: 第一句以介词/冠词结尾
    incomplete_endings = ('to', 'of', 'for', 'with', 'in', 'on', 'at', 'by', 
                          'a', 'an', 'the', 'is', 'are', 'was', 'were')
    if last_word in incomplete_endings:
        return True
    
    return False


def post_vad_processing(segments: List[Dict], 
                        min_duration: float = 0.5, 
                        max_gap: float = 1.0,
                        max_segment_duration: float = 10.0) -> List[Dict]:
    """
    基于 VAD 的智能分段后处理
    
    Args:
        segments: 原始段落列表
        min_duration: 最小段落时长（秒）
        max_gap: 最大合并间隔（秒）
        max_segment_duration: 最大段落时长（秒）
        
    Returns:
        处理后的段落列表
    """
    if not segments:
        return segments
    
    processed = []
    current = None
    
    for seg in segments:
        seg = seg.copy()  # 避免修改原始数据
        
        if current is None:
            current = seg
        else:
            gap = seg['start'] - current['end']
            current_duration = current['end'] - current['start']
            new_duration = seg['end'] - current['start']
            
            # 判断是否应该合并
            should_merge = (
                gap < max_gap and 
                new_duration <= max_segment_duration and
                should_merge_sentences(current['text'], seg['text'])
            )
            
            if should_merge:
                # 合并段落
                current['end'] = seg['end']
                current['text'] = current['text'].rstrip('.,!?') + ' ' + seg['text']
                
                # 合并词级时间戳
                if 'words' in current and 'words' in seg:
                    current['words'] = current.get('words', []) + seg.get('words', [])
            else:
                # 保存当前段落（如果满足最小时长）
                if current_duration >= min_duration:
                    processed.append(current)
                current = seg
    
    # 处理最后一个段落
    if current:
        duration = current['end'] - current['start']
        if duration >= min_duration:
            processed.append(current)
    
    return processed


def evaluate_segment_quality(segments: List[Dict], verbose: bool = True) -> Dict:
    """
    评估优化后的段落质量
    
    Args:
        segments: 字幕段落列表
        verbose: 是否打印详细信息
        
    Returns:
        质量指标字典
    """
    if not segments:
        return {
            'total_segments': 0,
            'avg_words': 0,
            'avg_duration': 0,
            'complete_sentences': 0,
            'complete_sentence_ratio': 0,
            'segments_with_errors': 0,
            'error_ratio': 0,
            'quality_score': 0
        }
    
    # 常见错误模式
    error_patterns = [
        'trick-lifr', 'main', 'obtaining', 'programs', 'available',
        'see the light day', 'kind of a', 'sort of a',
        'a lot of of', 'going to to'
    ]
    
    total = len(segments)
    word_counts = []
    durations = []
    complete_sentences = 0
    segments_with_errors = 0
    
    for seg in segments:
        text = seg.get('text', '').strip()
        start = seg.get('start', 0)
        end = seg.get('end', 0)
        
        # 词数
        words = len(text.split())
        word_counts.append(words)
        
        # 时长
        duration = end - start
        durations.append(duration)
        
        # 完整句子
        if text and text[-1] in '.!?。！？':
            complete_sentences += 1
        
        # 错误检测
        text_lower = text.lower()
        if any(err in text_lower for err in error_patterns):
            segments_with_errors += 1
    
    # 计算指标
    avg_words = sum(word_counts) / total
    avg_duration = sum(durations) / total
    complete_ratio = complete_sentences / total
    error_ratio = segments_with_errors / total
    
    # 计算质量评分 (0-100)
    score = 100.0
    
    # 词数评分
    if avg_words < 5:
        score -= (5 - avg_words) * 5
    elif avg_words > 20:
        score -= (avg_words - 20) * 3
    
    # 时长评分
    if avg_duration < 1.5:
        score -= (1.5 - avg_duration) * 10
    elif avg_duration > 8:
        score -= (avg_duration - 8) * 5
    
    # 完整句子评分
    if complete_ratio < 0.7:
        score -= (0.7 - complete_ratio) * 50
    
    # 错误评分
    score -= error_ratio * 100
    
    score = max(0, min(100, score))
    
    metrics = {
        'total_segments': total,
        'avg_words': round(avg_words, 1),
        'avg_duration': round(avg_duration, 2),
        'complete_sentences': complete_sentences,
        'complete_sentence_ratio': round(complete_ratio, 3),
        'segments_with_errors': segments_with_errors,
        'error_ratio': round(error_ratio, 3),
        'quality_score': round(score, 1),
        'word_count_range': (min(word_counts), max(word_counts)),
        'duration_range': (round(min(durations), 2), round(max(durations), 2))
    }
    
    if verbose:
        print(f"\n{'='*50}")
        print("ASR 段落质量评估报告")
        print(f"{'='*50}")
        print(f"总段落数: {metrics['total_segments']}")
        print(f"平均每段词数: {metrics['avg_words']:.1f} (范围: {metrics['word_count_range'][0]}-{metrics['word_count_range'][1]})")
        print(f"平均时长: {metrics['avg_duration']:.2f}s (范围: {metrics['duration_range'][0]:.2f}-{metrics['duration_range'][1]:.2f}s)")
        print(f"完整句子比例: {metrics['complete_sentence_ratio']*100:.1f}%")
        print(f"有错误的段落数: {metrics['segments_with_errors']} ({metrics['error_ratio']*100:.1f}%)")
        print(f"\n质量评分: {metrics['quality_score']}/100")
        
        # 评级
        if score >= 90:
            grade = "A (优秀)"
        elif score >= 80:
            grade = "B (良好)"
        elif score >= 70:
            grade = "C (一般)"
        elif score >= 60:
            grade = "D (较差)"
        else:
            grade = "F (需改进)"
        print(f"质量等级: {grade}")
        print(f"{'='*50}\n")
    
    return metrics


def full_optimization_pipeline(segments: List[Dict],
                               min_duration: float = 1.5,
                               max_duration: float = 8.0,
                               min_words: int = 4,
                               max_words: int = 20,
                               custom_terms: Dict[str, str] = None,
                               verbose: bool = False) -> Tuple[List[Dict], Dict]:
    """
    完整的 ASR 优化流程
    
    Args:
        segments: 原始段落列表
        min_duration: 最小段落时长
        max_duration: 最大段落时长
        min_words: 最小词数
        max_words: 最大词数
        custom_terms: 自定义术语映射
        verbose: 是否打印详细信息
        
    Returns:
        (优化后的段落列表, 质量指标)
    """
    if not segments:
        return segments, {}
    
    if verbose:
        print("开始 ASR 后处理优化...")
        print(f"原始段落数: {len(segments)}")
    
    # 步骤 1: VAD 后处理
    segments = post_vad_processing(segments, 
                                   min_duration=0.5, 
                                   max_gap=1.0,
                                   max_segment_duration=max_duration)
    if verbose:
        print(f"VAD 后处理后: {len(segments)} 段")
    
    # 步骤 2: 技术术语修正
    term_corrector = TechnicalTermCorrector(custom_terms)
    segments = term_corrector.correct_segments(segments)
    
    # 步骤 3: 上下文感知合并
    context_merger = ContextAwareMerger()
    segments = context_merger.merge(segments)
    if verbose:
        print(f"上下文合并后: {len(segments)} 段")
    
    # 步骤 4: 完整后处理
    processor = ASRPostProcessor(
        min_segment_duration=min_duration,
        max_segment_duration=max_duration,
        min_words=min_words,
        max_words=max_words
    )
    segments = processor.optimize(segments)
    if verbose:
        print(f"最终优化后: {len(segments)} 段")
    
    # 步骤 5: 质量评估
    metrics = evaluate_segment_quality(segments, verbose=verbose)
    
    return segments, metrics


# ============================================================================
# SRT 处理器
# ============================================================================

class SRTProcessor:
    """
    完整的 SRT 文件处理器
    
    功能：
    - 解析 SRT 格式
    - 智能合并
    - 技术错误修正
    - 输出优化后的 SRT
    """
    
    def __init__(self):
        self.segments = []
    
    def parse_srt(self, srt_content: str) -> List[Dict]:
        """解析 SRT 格式内容"""
        segments = []
        blocks = re.split(r'\n\s*\n', srt_content.strip())
        
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                try:
                    # 解析序号
                    index = int(lines[0].strip())
                    
                    # 解析时间戳
                    time_match = re.match(
                        r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})',
                        lines[1]
                    )
                    if time_match:
                        start = self.time_to_seconds(time_match.group(1))
                        end = self.time_to_seconds(time_match.group(2))
                        
                        # 合并文本行
                        text = ' '.join(lines[2:]).strip()
                        
                        segments.append({
                            'index': index,
                            'start': start,
                            'end': end,
                            'text': text
                        })
                except (ValueError, IndexError):
                    continue
        
        return segments
    
    def time_to_seconds(self, time_str: str) -> float:
        """将 SRT 时间格式转换为秒数"""
        h, m, s_ms = time_str.split(':')
        s, ms = s_ms.split(',')
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    
    def seconds_to_srt_time(self, seconds: float) -> str:
        """将秒数转换为 SRT 时间格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        milliseconds = int((secs - int(secs)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{int(secs):02d},{milliseconds:03d}"
    
    def process(self, srt_content: str) -> List[Dict]:
        """完整的处理流程"""
        # 1. 解析
        segments = self.parse_srt(srt_content)
        
        # 2. 修正技术错误
        segments = fix_technical_errors(segments)
        
        # 3. 智能合并
        segments = intelligent_merge_segments(segments)
        
        # 4. 最终清理
        segments = self.final_cleanup(segments)
        
        return segments
    
    def final_cleanup(self, segments: List[Dict]) -> List[Dict]:
        """最终清理和格式化"""
        for seg in segments:
            text = seg['text']
            
            # 移除多余空格
            text = ' '.join(text.split())
            
            # 修复标点周围的空格
            text = re.sub(r'\s+([.,!?;:])', r'\1', text)
            text = re.sub(r'([.,!?;:])(?=[A-Za-z])', r'\1 ', text)
            
            # 确保专有名词格式
            text = re.sub(r'\b(VS|vs)\s+[Cc]ode\b', 'VS Code', text)
            text = re.sub(r'\bPRS\b', 'PRs', text)
            text = re.sub(r'\b(on[-\s]?ready)\b', 'onready', text, flags=re.IGNORECASE)
            text = re.sub(r'\b(on[-\s]?readies)\b', 'onreadies', text, flags=re.IGNORECASE)
            
            # 修复引号
            text = text.replace('"', '"').replace("'", "'")
            
            seg['text'] = text
        
        return segments
    
    def to_srt(self, segments: List[Dict]) -> str:
        """将处理后的段落转换回 SRT 格式"""
        srt_lines = []
        
        for i, seg in enumerate(segments, 1):
            start_time = self.seconds_to_srt_time(seg['start'])
            end_time = self.seconds_to_srt_time(seg['end'])
            
            srt_lines.append(str(i))
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(seg['text'])
            srt_lines.append("")
        
        return '\n'.join(srt_lines)


def fix_technical_errors(segments: List[Dict]) -> List[Dict]:
    """修正技术内容的特定错误"""
    corrections = {
        # 常见拼写错误
        'objeacts': 'objects',
        'affeacts': 'affects',
        'kind ofacts': 'kind of acts',
        'quality of life quality of life': 'quality of life',
        
        # 格式修正
        'on-ready': 'onready',
        'on readies': 'onreadies',
        'PRS': 'PRs',
        'H sliders': 'H-sliders',
        'Gado': 'Godot',
        'cubalgames. com': 'cubalgames.com',
        'cubalgames .com': 'cubalgames.com',
        
        # 重复修正
        'the the': 'the',
        'a a': 'a',
        'is is': 'is',
        'to to': 'to',
        'of of': 'of',
    }
    
    for seg in segments:
        text = seg['text']
        
        # 应用修正
        for wrong, correct in corrections.items():
            if wrong in text:
                text = text.replace(wrong, correct)
        
        # 确保专有名词格式正确
        text = re.sub(r'\bVS\s+[Cc]ode\b', 'VS Code', text)
        text = re.sub(r'\bvs\s+code\b', 'VS Code', text, flags=re.IGNORECASE)
        
        seg['text'] = text
    
    return segments


def intelligent_merge_segments(segments: List[Dict], 
                                max_duration: float = 10.0,
                                max_words: int = 25,
                                max_chars: int = 150) -> List[Dict]:
    """
    智能分段 - 在完整性和可读性间取得平衡
    
    Args:
        segments: 段落列表
        max_duration: 最大段落时长
        max_words: 最大词数
        max_chars: 最大字符数
        
    Returns:
        合并后的段落列表
    """
    if not segments:
        return segments
    
    optimized = []
    buffer = []
    
    # 常见句子开头词（不应该合并）
    common_starters = ('i ', "i'm ", "i'll ", "i've ", "i'd ", 'you ', 'we ', 'they ', 'he ', 'she ', 'it ')
    
    # 话题切换关键词
    topic_shift_keywords = ('next up', 'another thing', 'also,', 'moving on', 'by the way', 
                            'anyway', 'speaking of', 'on another note')
    
    # 句子开头词（不应该合并到前一句）
    sentence_starters = ('so ', 'but ', 'and ', 'or ', 'next ', 'well ', 'okay ', 'now ', 
                         'first ', 'second ', 'third ', 'finally ', 'however ', 'therefore ')
    
    for i, seg in enumerate(segments):
        current_text = seg['text'].strip()
        
        # 如果 buffer 为空，开始新 buffer
        if not buffer:
            buffer.append(seg.copy())
            continue
        
        last_seg = buffer[-1]
        last_text = last_seg['text'].strip()
        
        # ========== 判断是否应该合并 ==========
        should_merge = False
        
        # 1. 明显是同一句话被拆分（以小写开头）
        if current_text and current_text[0].islower():
            # 排除常见句子开头
            if not any(current_text.lower().startswith(starter) for starter in common_starters):
                should_merge = True
        
        # 2. 前一句以逗号、连词结尾
        elif last_text.endswith((',', ';', '-', '...')):
            should_merge = True
        elif last_text.lower().endswith((' but', ' and', ' or', ' because', ' so', ' though', 
                                          ' as', ' while', ' if', ' which', ' that', ' who',
                                          ' where', ' when', ' to', ' of', ' for', ' with')):
            should_merge = True
        
        # 3. 技术术语的延续
        elif (last_text.lower().endswith(('export', 'onready', 'drag', 'quality', 'to', 
                                           'the', 'a', 'an', 'this', 'that')) or
              current_text.lower().startswith(('variable', 'references', 'and drop', 'of life', 'see'))):
            should_merge = True
        
        # 4. 时间间隔非常短（<0.2秒）
        elif seg['start'] - last_seg['end'] < 0.2:
            if not last_text.endswith(('.', '!', '?')):
                should_merge = True
        
        # ========== 不应该合并的情况（覆盖上面的判断） ==========
        
        # 1. 合并后句子太长
        combined_words = sum(len(s['text'].split()) for s in buffer) + len(current_text.split())
        if combined_words > max_words:
            should_merge = False
        
        # 2. 合并后字符数太多
        combined_chars = sum(len(s['text']) for s in buffer) + len(current_text)
        if combined_chars > max_chars:
            should_merge = False
        
        # 3. 合并后时长太长
        combined_duration = seg['end'] - buffer[0]['start']
        if combined_duration > max_duration:
            should_merge = False
        
        # 4. 当前文本是明显的句子开头
        if current_text.lower().startswith(sentence_starters):
            should_merge = False
        
        # 5. 话题切换的标志
        if any(keyword in current_text.lower() for keyword in topic_shift_keywords):
            should_merge = False
        
        # 执行合并或保存
        if should_merge:
            buffer.append(seg.copy())
        else:
            # 保存 buffer 内容并开始新 buffer
            merged_seg = _merge_segments_with_punctuation(buffer)
            optimized.append(merged_seg)
            buffer = [seg.copy()]
    
    # 处理剩余的 buffer
    if buffer:
        merged_seg = _merge_segments_with_punctuation(buffer)
        optimized.append(merged_seg)
    
    return optimized


def _merge_segments_with_punctuation(segments: List[Dict]) -> Dict:
    """合并段落并智能添加标点"""
    if not segments:
        return None
    
    if len(segments) == 1:
        seg = segments[0].copy()
        text = seg['text'].strip()
        # 确保有结束标点
        if text and not text.endswith(('.', '!', '?')):
            if any(q_word in text.lower() for q_word in ['?', 'what', 'how', 'why', 'who', 'where', 'when']):
                text = text.rstrip('.,;:') + '?'
            else:
                text = text.rstrip('.,;:') + '.'
        seg['text'] = text
        return seg
    
    # 合并多个段落
    merged_text = ' '.join(s['text'].strip() for s in segments)
    
    # 清理多余的标点和空格
    merged_text = merged_text.replace(' .', '.').replace(' ,', ',')
    merged_text = merged_text.replace(' ?', '?').replace(' !', '!')
    merged_text = ' '.join(merged_text.split())  # 清理多余空格
    
    # 确保有合适的结束标点
    if not merged_text.endswith(('.', '!', '?')):
        if any(q_word in merged_text.lower() for q_word in ['?', 'what', 'how', 'why', 'who', 'where', 'when']):
            merged_text = merged_text.rstrip('.,;:') + '?'
        else:
            merged_text = merged_text.rstrip('.,;:') + '.'
    
    # 合并词级时间戳
    merged_words = []
    for seg in segments:
        if 'words' in seg:
            merged_words.extend(seg.get('words', []))
    
    return {
        'start': segments[0]['start'],
        'end': segments[-1]['end'],
        'text': merged_text,
        'words': merged_words
    }


# ============================================================================
# 长段落拆分
# ============================================================================

def split_by_sentence_boundary(text: str) -> List[str]:
    """
    按句子边界拆分（比简单的句号分割更智能）
    
    Args:
        text: 原始文本
        
    Returns:
        句子列表
    """
    # 保护特殊缩写和技术术语
    protected_patterns = [
        (r'(VS Code)\.', r'\1[DOT]'),
        (r'(Node\.js)', r'Node[DOT]js'),
        (r'(Next\.js)', r'Next[DOT]js'),
        (r'(Vue\.js)', r'Vue[DOT]js'),
        (r'(React\.js)', r'React[DOT]js'),
        (r'(Express\.js)', r'Express[DOT]js'),
        (r'(\d+)\.(\d+)', r'\1[DOT]\2'),  # 版本号
        (r'(Mr|Mrs|Ms|Dr|Prof|Sr|Jr)\.', r'\1[DOT]'),  # 称谓
        (r'(etc|vs|e\.g|i\.e)\.', r'\1[DOT]'),  # 常见缩写
    ]
    
    for pattern, replacement in protected_patterns:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    # 按句子边界拆分
    # 模式：句号、问号、感叹号后跟空格和大写字母
    pattern = r'(?<=[.!?])\s+(?=[A-Z])'
    sentences = re.split(pattern, text)
    
    # 恢复保护的标记
    sentences = [s.replace('[DOT]', '.') for s in sentences]
    
    return [s.strip() for s in sentences if s.strip()]


def split_long_segment(segment: Dict, max_sentences: int = 2) -> List[Dict]:
    """
    拆分过长的段落
    
    Args:
        segment: 原始段落
        max_sentences: 每个段落最大句子数
        
    Returns:
        拆分后的段落列表
    """
    text = segment['text']
    start = segment['start']
    end = segment['end']
    duration = end - start
    
    sentences = split_by_sentence_boundary(text)
    
    if len(sentences) <= max_sentences:
        return [segment]
    
    # 按句子拆分，重新分配时间
    split_segments = []
    total_chars = sum(len(s) for s in sentences)
    current_start = start
    
    for i in range(0, len(sentences), max_sentences):
        segment_sentences = sentences[i:i + max_sentences]
        segment_text = ' '.join(segment_sentences)
        
        # 按字符数比例分配时间
        segment_chars = sum(len(s) for s in segment_sentences)
        segment_duration = duration * (segment_chars / total_chars) if total_chars > 0 else duration / len(sentences)
        
        split_segments.append({
            'start': current_start,
            'end': current_start + segment_duration,
            'text': segment_text,
            'words': []
        })
        
        current_start += segment_duration
    
    return split_segments


def optimize_tech_discussion_segments(segments: List[Dict], 
                                       max_sentences: int = 2) -> List[Dict]:
    """
    专门优化技术讨论的段落
    
    Args:
        segments: 段落列表
        max_sentences: 每个段落最大句子数
        
    Returns:
        优化后的段落列表
    """
    optimized = []
    
    for seg in segments:
        text = seg['text']
        sentences = split_by_sentence_boundary(text)
        
        if len(sentences) <= max_sentences:
            # 1-2 个句子，保持原样
            optimized.append(seg)
        else:
            # 将长段落拆分成多个短段落
            split_segs = split_long_segment(seg, max_sentences)
            optimized.extend(split_segs)
    
    return optimized


def intelligent_segmentation(segments: List[Dict],
                              max_words: int = 25,
                              max_chars: int = 150,
                              max_duration: float = 10.0,
                              split_long: bool = True,
                              max_sentences: int = 2) -> List[Dict]:
    """
    完整的智能分段流程
    
    Args:
        segments: 原始段落列表
        max_words: 最大词数
        max_chars: 最大字符数
        max_duration: 最大时长
        split_long: 是否拆分过长段落
        max_sentences: 拆分时每段最大句子数
        
    Returns:
        优化后的段落列表
    """
    if not segments:
        return segments
    
    # 1. 智能合并
    merged = intelligent_merge_segments(
        segments, 
        max_duration=max_duration,
        max_words=max_words,
        max_chars=max_chars
    )
    
    # 2. 拆分过长段落（可选）
    if split_long:
        merged = optimize_tech_discussion_segments(merged, max_sentences=max_sentences)
    
    return merged


# 保留旧函数名的兼容性
def _merge_buffer_segments(buffer: List[Dict]) -> Dict:
    """兼容性函数 - 使用新的合并函数"""
    return _merge_segments_with_punctuation(buffer)


# 继续原有代码
def realtime_optimization(segments: List[Dict], lookahead: int = 2) -> List[Dict]:
    """
    实时优化 ASR 输出（适合流式处理）
    
    Args:
        segments: 段落列表
        lookahead: 向前查看的段落数
        
    Returns:
        优化后的段落列表
    """
    if not segments:
        return segments
    
    optimized = []
    i = 0
    
    while i < len(segments):
        current = segments[i].copy()
        merge_count = 0
        
        # 检查后续段落是否需要合并
        for j in range(1, lookahead + 1):
            if i + j >= len(segments):
                break
            
            next_seg = segments[i + j]
            
            if should_merge_sentences(current['text'], next_seg['text']):
                # 合并
                current['text'] = current['text'].rstrip('.,!?') + ' ' + next_seg['text']
                current['end'] = next_seg['end']
                merge_count += 1
            else:
                break
        
        optimized.append(current)
        i += 1 + merge_count
    
    return optimized


# ============================================================================
# 完整优化策略
# ============================================================================

def split_by_sentences_with_timing(segment: Dict, 
                                    sentences: List[str], 
                                    max_sentences: int = 2) -> List[Dict]:
    """
    按句子拆分段落并重新分配时间
    
    Args:
        segment: 原始段落
        sentences: 已拆分的句子列表
        max_sentences: 每段最大句子数
        
    Returns:
        拆分后的段落列表
    """
    if len(sentences) <= max_sentences:
        return [segment]
    
    start = segment['start']
    end = segment['end']
    duration = end - start
    total_chars = sum(len(s) for s in sentences)
    
    split_segments = []
    current_start = start
    
    for i in range(0, len(sentences), max_sentences):
        segment_sentences = sentences[i:i + max_sentences]
        segment_text = ' '.join(segment_sentences)
        
        # 按字符数比例分配时间
        segment_chars = sum(len(s) for s in segment_sentences)
        segment_duration = duration * (segment_chars / total_chars) if total_chars > 0 else duration / len(sentences)
        
        split_segments.append({
            'start': current_start,
            'end': current_start + segment_duration,
            'text': segment_text,
            'words': []
        })
        
        current_start += segment_duration
    
    return split_segments


def split_by_punctuation(segment: Dict, max_words: int = 20) -> List[Dict]:
    """
    按标点符号智能切分长句子
    
    优先在逗号、分号处切分，确保每段不超过 max_words
    
    Args:
        segment: 原始段落
        max_words: 每段最大词数
        
    Returns:
        拆分后的段落列表
    """
    text = segment['text'].strip()
    words = text.split()
    
    if len(words) <= max_words:
        return [segment]
    
    start = segment['start']
    end = segment['end']
    duration = end - start
    total_chars = len(text)
    
    # 找到所有可能的切分点（标点符号位置）
    split_points = []
    
    # 优先级：句号 > 分号 > 逗号
    # 找逗号位置
    for i, char in enumerate(text):
        if char == ',':
            # 计算逗号前的词数
            words_before = len(text[:i+1].split())
            split_points.append({
                'pos': i + 1,  # 包含逗号
                'priority': 1,  # 逗号优先级低
                'words_before': words_before
            })
        elif char == ';':
            words_before = len(text[:i+1].split())
            split_points.append({
                'pos': i + 1,
                'priority': 2,  # 分号优先级中
                'words_before': words_before
            })
        elif char == '.' and i < len(text) - 1 and text[i+1] == ' ':
            # 句号后面有空格（排除缩写如 "Mr."）
            words_before = len(text[:i+1].split())
            split_points.append({
                'pos': i + 1,
                'priority': 3,  # 句号优先级高
                'words_before': words_before
            })
    
    if not split_points:
        # 没有标点，按词数切分
        return split_by_word_count(segment, max_words)
    
    # 选择最佳切分点
    split_segments = []
    current_start_pos = 0
    current_start_time = start
    
    while current_start_pos < len(text):
        remaining_text = text[current_start_pos:].strip()
        remaining_words = len(remaining_text.split())
        
        if remaining_words <= max_words:
            # 剩余部分不需要切分
            chunk_text = remaining_text
            if chunk_text:
                # 确保有结束标点
                if not chunk_text.endswith(('.', '!', '?')):
                    chunk_text = chunk_text.rstrip('.,;:') + '.'
                
                # 计算时间
                char_ratio = len(remaining_text) / total_chars if total_chars > 0 else 0
                segment_duration = duration * char_ratio
                
                split_segments.append({
                    'start': current_start_time,
                    'end': end,
                    'text': chunk_text,
                    'words': []
                })
            break
        
        # 找到最佳切分点
        best_point = None
        min_diff = float('inf')
        
        for point in split_points:
            if point['pos'] <= current_start_pos:
                continue
            
            words_in_chunk = point['words_before'] - len(text[:current_start_pos].split())
            
            # 选择最接近 max_words 但不超过的切分点
            if words_in_chunk <= max_words:
                diff = max_words - words_in_chunk
                # 优先选择优先级高的标点
                adjusted_diff = diff - point['priority'] * 0.1
                if adjusted_diff < min_diff:
                    min_diff = adjusted_diff
                    best_point = point
        
        if best_point is None:
            # 没有合适的切分点，强制按词数切分
            words_list = remaining_text.split()
            chunk_text = ' '.join(words_list[:max_words])
            if not chunk_text.endswith(('.', '!', '?', ',')):
                chunk_text = chunk_text + ','
            
            char_ratio = len(chunk_text) / total_chars if total_chars > 0 else 0
            segment_duration = duration * char_ratio
            
            split_segments.append({
                'start': current_start_time,
                'end': current_start_time + segment_duration,
                'text': chunk_text.strip(),
                'words': []
            })
            
            current_start_pos += len(chunk_text)
            current_start_time += segment_duration
        else:
            # 使用找到的切分点
            chunk_text = text[current_start_pos:best_point['pos']].strip()
            
            # 计算时间
            char_ratio = len(chunk_text) / total_chars if total_chars > 0 else 0
            segment_duration = duration * char_ratio
            
            split_segments.append({
                'start': current_start_time,
                'end': current_start_time + segment_duration,
                'text': chunk_text,
                'words': []
            })
            
            current_start_pos = best_point['pos']
            current_start_time += segment_duration
    
    # 清理：确保每段都有正确的标点
    for seg in split_segments:
        text = seg['text'].strip()
        if text and not text.endswith(('.', '!', '?')):
            # 如果是最后一段，加句号；否则保持逗号
            if seg == split_segments[-1]:
                seg['text'] = text.rstrip('.,;:') + '.'
    
    return split_segments if split_segments else [segment]


def split_by_word_count(segment: Dict, max_words: int = 25) -> List[Dict]:
    """
    按词数拆分段落（备用方案）
    
    Args:
        segment: 原始段落
        max_words: 每段最大词数
        
    Returns:
        拆分后的段落列表
    """
    text = segment['text']
    words = text.split()
    
    if len(words) <= max_words:
        return [segment]
    
    start = segment['start']
    end = segment['end']
    duration = end - start
    
    split_segments = []
    total_words = len(words)
    
    for i in range(0, total_words, max_words):
        chunk_words = words[i:i + max_words]
        chunk_text = ' '.join(chunk_words)
        
        # 按词数比例分配时间
        ratio_start = i / total_words
        ratio_end = min((i + len(chunk_words)) / total_words, 1.0)
        
        # 确保有结束标点
        if not chunk_text.endswith(('.', '!', '?')):
            chunk_text = chunk_text.rstrip('.,;:') + '.'
        
        split_segments.append({
            'start': start + duration * ratio_start,
            'end': start + duration * ratio_end,
            'text': chunk_text,
            'words': []
        })
    
    return split_segments


def split_overlong_paragraphs(segments: List[Dict], 
                               max_sentences: int = 3, 
                               max_words: int = 30) -> List[Dict]:
    """
    拆分过长的段落
    
    Args:
        segments: 段落列表
        max_sentences: 每段最大句子数
        max_words: 每段最大词数
        
    Returns:
        拆分后的段落列表
    """
    # 话题切换关键词
    topic_shifts = ('next up', 'also,', 'another', 'by the way', 'anyway', 
                    'moving on', 'speaking of', 'on another note')
    
    optimized = []
    
    for seg in segments:
        text = seg['text']
        words = text.split()
        
        # 检查是否需要拆分
        needs_split = False
        
        # 规则1：词数过多
        if len(words) > max_words:
            needs_split = True
        
        # 规则2：句子数过多
        sentences = split_by_sentence_boundary(text)
        if len(sentences) > max_sentences:
            needs_split = True
        
        # 规则3：包含明显的话题切换
        if any(shift in text.lower() for shift in topic_shifts) and len(sentences) > 2:
            needs_split = True
        
        if needs_split:
            # 优先按句子拆分
            if len(sentences) > 1:
                split_segs = split_by_sentences_with_timing(seg, sentences, max_sentences)
                # 检查拆分后的段落是否仍然过长
                final_segs = []
                for s in split_segs:
                    if len(s['text'].split()) > max_words:
                        # 按标点进一步拆分
                        final_segs.extend(split_by_punctuation(s, max_words))
                    else:
                        final_segs.append(s)
                optimized.extend(final_segs)
            else:
                # 如果只有一个长句，优先按标点拆分
                split_segs = split_by_punctuation(seg, max_words)
                optimized.extend(split_segs)
        else:
            optimized.append(seg)
    
    return optimized


def intelligent_merge_short_fragments(segments: List[Dict],
                                       min_words: int = 5,
                                       max_words: int = 25) -> List[Dict]:
    """
    智能合并过短的片段
    
    Args:
        segments: 段落列表
        min_words: 最小词数（低于此值考虑合并）
        max_words: 合并后最大词数
        
    Returns:
        合并后的段落列表
    """
    if not segments:
        return segments
    
    merged = []
    buffer = None
    
    for seg in segments:
        text = seg['text'].strip()
        word_count = len(text.split())
        
        if buffer is None:
            buffer = seg.copy()
            continue
        
        buffer_text = buffer['text'].strip()
        buffer_words = len(buffer_text.split())
        
        # 判断是否应该合并
        should_merge = False
        
        # 当前 buffer 太短
        if buffer_words < min_words:
            should_merge = True
        
        # 当前段落太短
        if word_count < min_words:
            should_merge = True
        
        # 当前段落以小写开头（可能是前一句的延续）
        if text and text[0].islower():
            should_merge = True
        
        # 检查合并后是否超限
        combined_words = buffer_words + word_count
        if combined_words > max_words:
            should_merge = False
        
        if should_merge:
            # 合并
            buffer['text'] = buffer_text.rstrip('.,;:') + ' ' + text
            buffer['end'] = seg['end']
        else:
            # 保存 buffer 并开始新的
            if not buffer_text.endswith(('.', '!', '?')):
                buffer['text'] = buffer_text + '.'
            merged.append(buffer)
            buffer = seg.copy()
    
    # 处理最后的 buffer
    if buffer:
        buffer_text = buffer['text'].strip()
        if not buffer_text.endswith(('.', '!', '?')):
            buffer['text'] = buffer_text + '.'
        merged.append(buffer)
    
    return merged


def final_formatting(segments: List[Dict]) -> List[Dict]:
    """
    最终格式化和标点修正
    
    Args:
        segments: 段落列表
        
    Returns:
        格式化后的段落列表
    """
    for seg in segments:
        text = seg['text'].strip()
        
        # 清理多余空格
        text = ' '.join(text.split())
        
        # 修复标点空格
        text = re.sub(r'\s+([.,!?;:])', r'\1', text)
        text = re.sub(r'([.,!?;:])(?=[A-Za-z])', r'\1 ', text)
        
        # 修复重复标点
        text = re.sub(r'([.,!?])\1+', r'\1', text)
        
        # 确保句首大写
        if text and text[0].isalpha():
            text = text[0].upper() + text[1:]
        
        # 确保有结束标点
        if text and not text.endswith(('.', '!', '?')):
            # 检查是否是问句
            if any(q in text.lower() for q in ['what', 'how', 'why', 'who', 'where', 'when', '?']):
                text = text.rstrip('.,;:') + '?'
            else:
                text = text.rstrip('.,;:') + '.'
        
        seg['text'] = text
    
    return segments


def complete_optimization_strategy(segments: List[Dict],
                                    max_words: int = 20,
                                    max_sentences: int = 2,
                                    min_words: int = 5,
                                    use_external_dict: bool = True) -> Tuple[List[Dict], Dict]:
    """
    完整的四阶段优化策略
    
    阶段1: 修正明显错误
    阶段2: 智能合并过短片段
    阶段3: 合理拆分过长段落（按句子）
    阶段4: 按标点切分超长句子
    阶段5: 最终格式化和标点修正
    
    Args:
        segments: 原始段落列表
        max_words: 最大词数（默认20，适合TTS）
        max_sentences: 最大句子数（默认2）
        min_words: 最小词数
        use_external_dict: 是否使用外部词库
        
    Returns:
        (优化后的段落列表, 质量指标)
    """
    if not segments:
        return segments, {}
    
    original_count = len(segments)
    
    # 阶段1：修正明显错误
    if use_external_dict and DICT_MANAGER_AVAILABLE:
        try:
            dm = get_dictionary_manager()
            segments = dm.correct_segments(segments)
        except Exception:
            pass
    
    # 阶段2：智能合并过短片段
    segments = intelligent_merge_short_fragments(segments, min_words=min_words, max_words=max_words)
    after_merge_count = len(segments)
    
    # 阶段3：合理拆分过长段落（按句子）
    segments = split_overlong_paragraphs(segments, max_sentences=max_sentences, max_words=max_words)
    
    # 阶段4：按标点切分仍然过长的句子
    final_segments = []
    for seg in segments:
        word_count = len(seg['text'].split())
        if word_count > max_words:
            # 按标点切分
            split_segs = split_by_punctuation(seg, max_words)
            final_segments.extend(split_segs)
        else:
            final_segments.append(seg)
    segments = final_segments
    after_split_count = len(segments)
    
    # 阶段4：最终格式化
    segments = final_formatting(segments)
    
    # 评估质量
    quality = evaluate_segment_quality_detailed(segments)
    quality['original_count'] = original_count
    quality['after_merge_count'] = after_merge_count
    quality['after_split_count'] = after_split_count
    quality['final_count'] = len(segments)
    
    return segments, quality


def evaluate_segment_quality_detailed(segments: List[Dict]) -> Dict:
    """
    详细评估段落质量
    
    评估标准：
    - 优秀: 10-20词，1-2个句子
    - 良好: 5-25词，1-3个句子
    - 一般: 26-35词
    - 需改进: >35词或<5词
    
    Args:
        segments: 段落列表
        
    Returns:
        质量指标字典
    """
    if not segments:
        return {
            'total': 0,
            'excellent': 0,
            'good': 0,
            'fair': 0,
            'poor': 0,
            'quality_score': 0
        }
    
    quality_metrics = {
        'excellent': 0,
        'good': 0,
        'fair': 0,
        'poor': 0
    }
    
    word_counts = []
    durations = []
    
    for seg in segments:
        text = seg['text']
        words = text.split()
        word_count = len(words)
        word_counts.append(word_count)
        
        duration = seg.get('end', 0) - seg.get('start', 0)
        durations.append(duration)
        
        sentences = split_by_sentence_boundary(text)
        sentence_count = len(sentences)
        
        # 评估质量等级
        if 10 <= word_count <= 20 and 1 <= sentence_count <= 2:
            quality_metrics['excellent'] += 1
        elif 5 <= word_count <= 25 and 1 <= sentence_count <= 3:
            quality_metrics['good'] += 1
        elif 26 <= word_count <= 35:
            quality_metrics['fair'] += 1
        else:
            quality_metrics['poor'] += 1
    
    total = len(segments)
    
    # 计算质量分数 (0-100)
    quality_score = (
        quality_metrics['excellent'] * 100 +
        quality_metrics['good'] * 80 +
        quality_metrics['fair'] * 50 +
        quality_metrics['poor'] * 20
    ) / total
    
    return {
        'total': total,
        'excellent': quality_metrics['excellent'],
        'good': quality_metrics['good'],
        'fair': quality_metrics['fair'],
        'poor': quality_metrics['poor'],
        'excellent_ratio': round(quality_metrics['excellent'] / total, 3),
        'good_ratio': round(quality_metrics['good'] / total, 3),
        'avg_words': round(sum(word_counts) / total, 1),
        'avg_duration': round(sum(durations) / total, 2),
        'word_range': (min(word_counts), max(word_counts)),
        'quality_score': round(quality_score, 1)
    }


def print_quality_report(quality: Dict):
    """打印质量报告"""
    print("\n" + "=" * 50)
    print("段落质量分析报告")
    print("=" * 50)
    
    total = quality.get('total', 0)
    if total == 0:
        print("无段落数据")
        return
    
    print(f"总段落数: {total}")
    
    if 'original_count' in quality:
        print(f"  原始: {quality['original_count']} -> 合并后: {quality.get('after_merge_count', 'N/A')} -> 最终: {quality.get('final_count', total)}")
    
    print(f"\n词数统计:")
    print(f"  平均词数: {quality.get('avg_words', 'N/A')}")
    print(f"  词数范围: {quality.get('word_range', 'N/A')}")
    print(f"  平均时长: {quality.get('avg_duration', 'N/A')}s")
    
    print(f"\n质量分布:")
    print(f"  优秀 (10-20词, 1-2句): {quality['excellent']}/{total} ({quality.get('excellent_ratio', 0)*100:.1f}%)")
    print(f"  良好 (5-25词, 1-3句):  {quality['good']}/{total} ({quality.get('good_ratio', 0)*100:.1f}%)")
    print(f"  一般 (26-35词):        {quality['fair']}/{total}")
    print(f"  需改进 (>35或<5词):    {quality['poor']}/{total}")
    
    print(f"\n综合质量分数: {quality.get('quality_score', 0)}/100")
    
    # 评级
    score = quality.get('quality_score', 0)
    if score >= 90:
        grade = "A (优秀)"
    elif score >= 80:
        grade = "B (良好)"
    elif score >= 70:
        grade = "C (一般)"
    elif score >= 60:
        grade = "D (较差)"
    else:
        grade = "F (需改进)"
    print(f"质量等级: {grade}")
    print("=" * 50 + "\n")


def evaluate_srt_quality(srt_content: str) -> Tuple[float, Dict]:
    """
    评估 SRT 文件的质量
    
    Args:
        srt_content: SRT 文件内容
        
    Returns:
        (质量分数, 指标字典)
    """
    processor = SRTProcessor()
    segments = processor.parse_srt(srt_content)
    
    if not segments:
        return 0, {}
    
    # 错误模式
    error_patterns = ['prs ', 'affects', 'objects', 'on-ready', 'kind ofacts']
    
    metrics = {
        'total_segments': len(segments),
        'avg_chars_per_segment': sum(len(s['text']) for s in segments) / len(segments),
        'avg_words_per_segment': sum(len(s['text'].split()) for s in segments) / len(segments),
        'segments_with_proper_punctuation': sum(
            1 for s in segments if s['text'].strip().endswith(('.', '!', '?'))
        ),
        'technical_errors': sum(
            1 for s in segments 
            if any(err in s['text'].lower() for err in error_patterns)
        )
    }
    
    # 计算质量分数（0-100）
    punctuation_score = (metrics['segments_with_proper_punctuation'] / metrics['total_segments']) * 30
    word_count_score = min(metrics['avg_words_per_segment'], 15) * 2  # 最多30分
    error_score = max(0, 40 - (metrics['technical_errors'] * 5))
    
    total_score = punctuation_score + word_count_score + error_score
    
    return round(total_score, 1), metrics


def process_srt_file(input_path: str, output_path: str = None) -> str:
    """
    处理 SRT 文件的便捷函数
    
    Args:
        input_path: 输入 SRT 文件路径
        output_path: 输出 SRT 文件路径（可选）
        
    Returns:
        优化后的 SRT 内容
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        srt_content = f.read()
    
    processor = SRTProcessor()
    segments = processor.process(srt_content)
    optimized_srt = processor.to_srt(segments)
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(optimized_srt)
        print(f"优化后的 SRT 已保存到: {output_path}")
    
    return optimized_srt


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    # 测试数据 - 包含常见 ASR 错误和长句子
    test_segments = [
        {"start": 0.0, "end": 3.2, "text": "So I wasn't going to make a second video today, but Godot"},
        {"start": 3.2, "end": 5.099, "text": "4.6 Dev 1 just dropped,"},
        {"start": 5.16, "end": 9.039, "text": "which is absolutely absurd because we literally just got 4.5."},
        {"start": 9.06, "end": 10.82, "text": "So we obviously got to check this out."},
        {"start": 10.919, "end": 12.98, "text": "The other video I recorded is going to be out tomorrow."},
        {"start": 13.14, "end": 15.5, "text": "So stay tuned for that one. But reading through this."},
        {"start": 15.98, "end": 18.559, "text": "So the first development snapshot of 4.6 has arrived,"},
        {"start": 18.6, "end": 21.039, "text": "as is often the case for our first development snapshot."},
        {"start": 21.239, "end": 24.739, "text": "A significant portion of quality prs from our backlog are finally able"},
        {"start": 24.739, "end": 25.46, "text": "to see the light"},
        {"start": 25.46, "end": 28.6, "text": "day as they were either locked out from 4.5 or they"},
        {"start": 28.6, "end": 30.16, "text": "were too risky to merge for the stable release"},
        # 添加更多测试用例 - 包含常见错误
        {"start": 30.5, "end": 32.0, "text": "The Trick-lifr's of prs are mAIn"},
        {"start": 32.1, "end": 34.0, "text": "features for the commUnity."},
        {"start": 34.2, "end": 36.5, "text": "Check out the on ready variable and F keys support."},
        {"start": 36.6, "end": 38.0, "text": "Also the drag and drop export variable works now."},
        # 添加长句子测试用例
        {"start": 165.5, "end": 174.699, "text": "Joypad. While it's common for programs to have significant overlap between registering inputs of these types, it's not uncommon for systems to deliberately stylize the two types separately, often handling their."},
        {"start": 296.22, "end": 305.259, "text": "Let me know if you guys prefer using exported references or onready variables. I find a lot of people like onreadies over export and I honestly prefer export like."},
    ]
    
    print("=" * 60)
    print("ASR 后处理优化测试")
    print("=" * 60)
    
    print("\n原始段落:")
    for i, seg in enumerate(test_segments, 1):
        print(f"  {i:2d}. [{seg['start']:5.1f}s - {seg['end']:5.1f}s] {seg['text']}")
    
    # 测试完整优化策略
    print("\n" + "-" * 60)
    print("测试完整优化策略 (complete_optimization_strategy)...")
    print("-" * 60)
    
    optimized, quality = complete_optimization_strategy(
        test_segments.copy(),
        max_words=20,
        max_sentences=2,
        min_words=5,
        use_external_dict=True
    )
    
    print("\n优化后段落:")
    for i, seg in enumerate(optimized, 1):
        print(f"  {i:2d}. [{seg['start']:5.1f}s - {seg['end']:5.1f}s] {seg['text']}")
    
    # 打印质量报告
    print_quality_report(quality)
    
    # 测试 SRT 处理
    print("\n" + "=" * 60)
    print("SRT 处理测试")
    print("=" * 60)
    
    test_srt = """1
00:00:00,000 --> 00:00:05,040
So I wasn't going to make a second video today, but Godot 4.6 Dev1 just dropped.

2
00:00:05,320 --> 00:00:08,980
Which is absolutely absurd because we literally just got 4.5.

3
00:00:09,060 --> 00:00:10,779
So we obviously got to check this out.

4
00:00:10,939 --> 00:00:14,320
The other video I recorded is going to be out tomorrow, so stay tuned for that one.

5
00:00:14,460 --> 00:00:19,940
But reading through this, so the first development snapshot of 4.6 has arrived, as is often the case for our.

6
00:00:19,940 --> 00:00:25,199
First development snapshot, a significant portion of quality PRS from our backlog are finally able to see.

7
00:00:25,199 --> 00:00:29,039
The light of day, as they were either locked out from 4.5, or they were too risky.

8
00:00:29,039 --> 00:00:30,079
To merge for the stable release.
"""
    
    processor = SRTProcessor()
    processed_segments = processor.process(test_srt)
    
    print("\n处理后的 SRT 段落:")
    for i, seg in enumerate(processed_segments, 1):
        print(f"  {i}. [{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}")
    
    # 评估质量
    score, srt_metrics = evaluate_srt_quality(test_srt)
    print(f"\n原始 SRT 质量分数: {score}/100")
    
    # 生成优化后的 SRT
    optimized_srt = processor.to_srt(processed_segments)
    score2, _ = evaluate_srt_quality(optimized_srt)
    print(f"优化后 SRT 质量分数: {score2}/100")
    
    print("\n" + "=" * 60)
    print("所有测试完成!")
    print("=" * 60)
