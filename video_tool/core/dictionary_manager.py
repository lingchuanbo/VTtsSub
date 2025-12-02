"""
ASR 词库管理器

功能：
1. 加载外部 JSON 词库
2. 合并多个词库
3. 支持热重载
4. 提供术语修正和错误修复

使用：
    from video_tool.core.dictionary_manager import DictionaryManager
    
    dm = DictionaryManager()
    dm.load_all()
    
    # 修正文本
    corrected = dm.correct_text("some text with errors")
    
    # 添加自定义术语
    dm.add_custom_term("myterm", "MyTerm")
"""

import json
import os
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path


class DictionaryManager:
    """ASR 词库管理器"""
    
    # 默认词库目录
    DEFAULT_DICT_DIR = Path(__file__).parent.parent / "dictionaries"
    
    def __init__(self, dict_dir: str = None):
        """
        初始化词库管理器
        
        Args:
            dict_dir: 词库目录路径，默认为 video_tool/dictionaries
        """
        self.dict_dir = Path(dict_dir) if dict_dir else self.DEFAULT_DICT_DIR
        
        # 词库数据
        self.technical_terms: Dict[str, str] = {}
        self.error_corrections: Dict[str, str] = {}
        self.custom_terms: Dict[str, str] = {}
        self.custom_corrections: Dict[str, str] = {}
        self.regex_patterns: List[Dict] = []
        
        # 编译后的正则表达式
        self._compiled_patterns: List[Tuple[re.Pattern, str]] = []
        self._term_patterns: Dict[re.Pattern, str] = {}
        
        # 加载状态
        self._loaded = False
    
    def load_all(self) -> bool:
        """
        加载所有词库
        
        Returns:
            是否成功加载
        """
        success = True
        
        # 加载技术术语词库
        if not self._load_technical_terms():
            success = False
        
        # 加载错误修正词库
        if not self._load_error_corrections():
            success = False
        
        # 加载自定义词库
        if not self._load_custom_terms():
            success = False
        
        # 编译正则表达式
        self._compile_patterns()
        
        self._loaded = True
        return success
    
    def _load_technical_terms(self) -> bool:
        """加载技术术语词库"""
        file_path = self.dict_dir / "technical_terms.json"
        
        if not file_path.exists():
            print(f"警告: 技术术语词库不存在: {file_path}")
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 提取所有分类中的术语
            categories = data.get("categories", {})
            for category_name, category_data in categories.items():
                if isinstance(category_data, dict) and "terms" in category_data:
                    terms = category_data["terms"]
                    for key, value in terms.items():
                        if not key.startswith("_"):  # 跳过注释字段
                            self.technical_terms[key.lower()] = value
            
            print(f"已加载 {len(self.technical_terms)} 个技术术语")
            return True
            
        except Exception as e:
            print(f"加载技术术语词库失败: {e}")
            return False
    
    def _load_error_corrections(self) -> bool:
        """加载错误修正词库"""
        file_path = self.dict_dir / "error_corrections.json"
        
        if not file_path.exists():
            print(f"警告: 错误修正词库不存在: {file_path}")
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 提取所有分类中的修正
            for category_name, category_data in data.items():
                if category_name.startswith("_"):
                    continue
                    
                if isinstance(category_data, dict):
                    if "corrections" in category_data:
                        corrections = category_data["corrections"]
                        for key, value in corrections.items():
                            if not key.startswith("_"):
                                self.error_corrections[key] = value
                    
                    # 处理正则表达式模式
                    if "patterns" in category_data:
                        self.regex_patterns.extend(category_data["patterns"])
            
            print(f"已加载 {len(self.error_corrections)} 个错误修正")
            print(f"已加载 {len(self.regex_patterns)} 个正则表达式模式")
            return True
            
        except Exception as e:
            print(f"加载错误修正词库失败: {e}")
            return False
    
    def _load_custom_terms(self) -> bool:
        """加载自定义词库"""
        file_path = self.dict_dir / "custom_terms.json"
        
        if not file_path.exists():
            # 自定义词库是可选的
            return True
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 加载自定义术语
            terms = data.get("terms", {})
            for key, value in terms.items():
                if not key.startswith("_"):
                    self.custom_terms[key.lower()] = value
            
            # 加载自定义修正
            corrections = data.get("corrections", {})
            for key, value in corrections.items():
                if not key.startswith("_"):
                    self.custom_corrections[key] = value
            
            print(f"已加载 {len(self.custom_terms)} 个自定义术语")
            print(f"已加载 {len(self.custom_corrections)} 个自定义修正")
            return True
            
        except Exception as e:
            print(f"加载自定义词库失败: {e}")
            return False
    
    def _compile_patterns(self):
        """编译正则表达式模式"""
        self._compiled_patterns = []
        self._term_patterns = {}
        
        # 编译正则表达式修正模式
        for pattern_data in self.regex_patterns:
            try:
                pattern = pattern_data.get("pattern", "")
                replacement = pattern_data.get("replacement", "")
                flags_str = pattern_data.get("flags", "")
                
                flags = 0
                if "i" in flags_str:
                    flags |= re.IGNORECASE
                if "m" in flags_str:
                    flags |= re.MULTILINE
                
                compiled = re.compile(pattern, flags)
                self._compiled_patterns.append((compiled, replacement))
                
            except Exception as e:
                print(f"编译正则表达式失败: {pattern_data.get('name', 'unknown')} - {e}")
        
        # 编译术语匹配模式
        all_terms = {**self.technical_terms, **self.custom_terms}
        for term_lower, term_correct in all_terms.items():
            try:
                # 使用词边界匹配
                pattern = re.compile(r'\b' + re.escape(term_lower) + r'\b', re.IGNORECASE)
                self._term_patterns[pattern] = term_correct
            except Exception as e:
                print(f"编译术语模式失败: {term_lower} - {e}")
    
    def reload(self) -> bool:
        """
        重新加载所有词库
        
        Returns:
            是否成功重载
        """
        # 清空现有数据
        self.technical_terms.clear()
        self.error_corrections.clear()
        self.custom_terms.clear()
        self.custom_corrections.clear()
        self.regex_patterns.clear()
        self._compiled_patterns.clear()
        self._term_patterns.clear()
        
        return self.load_all()
    
    def correct_text(self, text: str) -> str:
        """
        修正文本中的错误和术语
        
        Args:
            text: 原始文本
            
        Returns:
            修正后的文本
        """
        if not self._loaded:
            self.load_all()
        
        # 1. 应用错误修正（精确匹配）
        all_corrections = {**self.error_corrections, **self.custom_corrections}
        for wrong, correct in all_corrections.items():
            if wrong in text:
                text = text.replace(wrong, correct)
        
        # 2. 应用正则表达式修正
        for pattern, replacement in self._compiled_patterns:
            text = pattern.sub(replacement, text)
        
        # 3. 应用术语修正（词边界匹配）
        for pattern, correct in self._term_patterns.items():
            text = pattern.sub(correct, text)
        
        return text
    
    def correct_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        修正段落列表中的文本
        
        Args:
            segments: 段落列表
            
        Returns:
            修正后的段落列表
        """
        for seg in segments:
            if 'text' in seg:
                seg['text'] = self.correct_text(seg['text'])
        return segments
    
    def add_custom_term(self, term_lower: str, term_correct: str, save: bool = True) -> bool:
        """
        添加自定义术语
        
        Args:
            term_lower: 小写形式的术语
            term_correct: 正确格式的术语
            save: 是否保存到文件
            
        Returns:
            是否成功添加
        """
        self.custom_terms[term_lower.lower()] = term_correct
        
        # 编译新的模式
        try:
            pattern = re.compile(r'\b' + re.escape(term_lower.lower()) + r'\b', re.IGNORECASE)
            self._term_patterns[pattern] = term_correct
        except Exception as e:
            print(f"编译术语模式失败: {term_lower} - {e}")
            return False
        
        if save:
            return self._save_custom_terms()
        
        return True
    
    def add_custom_correction(self, wrong: str, correct: str, save: bool = True) -> bool:
        """
        添加自定义修正
        
        Args:
            wrong: 错误形式
            correct: 正确形式
            save: 是否保存到文件
            
        Returns:
            是否成功添加
        """
        self.custom_corrections[wrong] = correct
        
        if save:
            return self._save_custom_terms()
        
        return True
    
    def _save_custom_terms(self) -> bool:
        """保存自定义词库到文件"""
        file_path = self.dict_dir / "custom_terms.json"
        
        try:
            data = {
                "_description": "用户自定义术语词库 - 添加您项目特定的术语",
                "_usage": "在 terms 中添加您的自定义术语，key 为小写形式，value 为正确格式",
                "_version": "1.0.0",
                "terms": self.custom_terms,
                "corrections": self.custom_corrections
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
            
        except Exception as e:
            print(f"保存自定义词库失败: {e}")
            return False
    
    def get_all_terms(self) -> Dict[str, str]:
        """获取所有术语（包括内置和自定义）"""
        return {**self.technical_terms, **self.custom_terms}
    
    def get_all_corrections(self) -> Dict[str, str]:
        """获取所有修正（包括内置和自定义）"""
        return {**self.error_corrections, **self.custom_corrections}
    
    def search_term(self, query: str) -> List[Tuple[str, str]]:
        """
        搜索术语
        
        Args:
            query: 搜索关键词
            
        Returns:
            匹配的术语列表 [(小写形式, 正确格式), ...]
        """
        query_lower = query.lower()
        results = []
        
        all_terms = self.get_all_terms()
        for term_lower, term_correct in all_terms.items():
            if query_lower in term_lower or query_lower in term_correct.lower():
                results.append((term_lower, term_correct))
        
        return results
    
    def get_stats(self) -> Dict:
        """获取词库统计信息"""
        return {
            "technical_terms": len(self.technical_terms),
            "error_corrections": len(self.error_corrections),
            "custom_terms": len(self.custom_terms),
            "custom_corrections": len(self.custom_corrections),
            "regex_patterns": len(self.regex_patterns),
            "total_terms": len(self.get_all_terms()),
            "total_corrections": len(self.get_all_corrections())
        }
    
    def print_stats(self):
        """打印词库统计信息"""
        stats = self.get_stats()
        print("\n" + "=" * 40)
        print("ASR 词库统计")
        print("=" * 40)
        print(f"技术术语: {stats['technical_terms']}")
        print(f"错误修正: {stats['error_corrections']}")
        print(f"自定义术语: {stats['custom_terms']}")
        print(f"自定义修正: {stats['custom_corrections']}")
        print(f"正则表达式模式: {stats['regex_patterns']}")
        print("-" * 40)
        print(f"总术语数: {stats['total_terms']}")
        print(f"总修正数: {stats['total_corrections']}")
        print("=" * 40 + "\n")


# 全局单例
_dictionary_manager: Optional[DictionaryManager] = None


def get_dictionary_manager() -> DictionaryManager:
    """获取词库管理器单例"""
    global _dictionary_manager
    if _dictionary_manager is None:
        _dictionary_manager = DictionaryManager()
        _dictionary_manager.load_all()
    return _dictionary_manager


def correct_text(text: str) -> str:
    """
    修正文本的便捷函数
    
    Args:
        text: 原始文本
        
    Returns:
        修正后的文本
    """
    return get_dictionary_manager().correct_text(text)


def correct_segments(segments: List[Dict]) -> List[Dict]:
    """
    修正段落列表的便捷函数
    
    Args:
        segments: 段落列表
        
    Returns:
        修正后的段落列表
    """
    return get_dictionary_manager().correct_segments(segments)


# 测试代码
if __name__ == "__main__":
    print("测试词库管理器...")
    
    dm = DictionaryManager()
    dm.load_all()
    dm.print_stats()
    
    # 测试文本修正
    test_texts = [
        "I'm using godot and vs code for development.",
        "The mAIn feature is avAIlable now.",
        "Check out the on ready variable and F keys support.",
        "We use react and typescript with nodejs.",
        "The prs are ready for review.",
        "Working with photoshop and 3ds max.",
    ]
    
    print("\n测试文本修正:")
    print("-" * 60)
    for text in test_texts:
        corrected = dm.correct_text(text)
        print(f"原文: {text}")
        print(f"修正: {corrected}")
        print()
    
    # 测试搜索
    print("\n搜索 'photo':")
    results = dm.search_term("photo")
    for term_lower, term_correct in results:
        print(f"  {term_lower} -> {term_correct}")
    
    print("\n测试完成!")
