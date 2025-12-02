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
                                max_words: int = 25) -> List[Dict]:
    """
    基于语义和语法的智能句子合并
    
    Args:
        segments: 段落列表
        max_duration: 最大段落时长
        max_words: 最大词数
        
    Returns:
        合并后的段落列表
    """
    if not segments:
        return segments
    
    merged = []
    current = None
    
    for seg in segments:
        if current is None:
            current = seg.copy()
            continue
        
        current_text = current['text'].strip()
        next_text = seg['text'].strip()
        
        # 检查合并后是否超限
        new_duration = seg['end'] - current['start']
        new_words = len(current_text.split()) + len(next_text.split())
        
        if new_duration > max_duration or new_words > max_words:
            # 超限，保存当前段落
            if not current_text.endswith(('.', '!', '?')):
                current['text'] = current_text + '.'
            merged.append(current)
            current = seg.copy()
            continue
        
        # 判断是否需要合并
        should_merge = False
        
        # 规则1: 当前段以逗号、连接词或连字符结尾
        if (current_text.endswith((',', ';', ':', '-', '...')) or
            current_text.lower().endswith((' but', ' and', ' or', ' so', 
                                           ' because', ' though', ' as', 
                                           ' while', ' if', ' which', ' that'))):
            should_merge = True
        
        # 规则2: 下一段以小写字母开头
        elif next_text and next_text[0].islower():
            # 排除 "i", "i'm" 等
            first_word = next_text.split()[0].lower() if next_text.split() else ''
            if first_word not in ('i', "i'm", "i'll", "i've", "i'd"):
                should_merge = True
        
        # 规则3: 当前段是明显的不完整短语
        elif (len(current_text.split()) < 4 and 
              not current_text.endswith(('.', '!', '?')) and
              not current_text.lower().startswith(('so ', 'but ', 'and ', 'or '))):
            should_merge = True
        
        # 规则4: 技术术语的延续
        elif (current_text.lower().endswith(('export ', 'onready ', 'pr ', 'xr ', 'vs ')) or
              next_text.lower().startswith(('variable', 'references', 'code'))):
            should_merge = True
        
        # 规则5: 时间间隔很短（小于0.3秒）
        elif seg['start'] - current['end'] < 0.3:
            if not current_text.endswith(('.', '!', '?')):
                should_merge = True
        
        if should_merge:
            # 合并文本
            current_text_clean = current_text.rstrip('.,!?;:')
            next_text_clean = next_text.lstrip()
            
            # 如果当前文本以连字符结尾，不要加空格
            if current_text_clean.endswith('-'):
                merged_text = current_text_clean + next_text_clean
            else:
                merged_text = current_text_clean + ' ' + next_text_clean
            
            current['text'] = merged_text
            current['end'] = seg['end']
        else:
            # 确保当前段有正确的结束标点
            if not current_text.endswith(('.', '!', '?')):
                # 检查是否是问句
                if any(q_word in current_text.lower() for q_word in ['?', 'what', 'how', 'why', 'where', 'when', 'who']):
                    current['text'] = current_text + '?'
                else:
                    current['text'] = current_text + '.'
            merged.append(current)
            current = seg.copy()
    
    # 处理最后一段
    if current:
        current_text = current['text'].strip()
        if not current_text.endswith(('.', '!', '?')):
            current['text'] = current_text + '.'
        merged.append(current)
    
    return merged


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
    # 测试数据 - 包含常见 ASR 错误
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
    ]
    
    print("=" * 60)
    print("ASR 后处理优化测试")
    print("=" * 60)
    
    print("\n原始段落:")
    for i, seg in enumerate(test_segments, 1):
        print(f"  {i:2d}. [{seg['start']:5.1f}s - {seg['end']:5.1f}s] {seg['text']}")
    
    print("\n" + "-" * 60)
    print("运行完整优化流程...")
    print("-" * 60)
    
    # 运行完整优化流程
    optimized, metrics = full_optimization_pipeline(
        test_segments,
        min_duration=1.5,
        max_duration=8.0,
        min_words=4,
        max_words=20,
        verbose=True
    )
    
    print("\n优化后段落:")
    for i, seg in enumerate(optimized, 1):
        print(f"  {i:2d}. [{seg['start']:5.1f}s - {seg['end']:5.1f}s] {seg['text']}")
    
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
