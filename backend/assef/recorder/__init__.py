"""LLM 调用链记录模块 —— PromptRecorder 以 JSONL 格式记录 LLM 交互并计算指标

支持按日期分文件写入记录，包含 useful 回溯更新、按上下文批量更新、
以及格式有效性/代码占比/意图猜测等自动指标计算功能。
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path

from ..logging_config import get_logger
from ..models.recorder import CallerType, Metrics, RecordEntry

_logger = get_logger("recorder")


def _extract_code_block_chars(text: str) -> int:
    """提取响应中所有代码块（```...```）内的字符总数

    Args:
        text: LLM 响应文本

    Returns:
        代码块内字符总数
    """
    pattern = re.compile(r"```(?:\w*\n)?(.*?)```", re.DOTALL)
    total = 0
    for match in pattern.finditer(text):
        total += len(match.group(1))
    return total


def _extract_json_chars(text: str) -> int:
    """提取响应中最大有效 JSON（数组或对象）的字符数

    Args:
        text: LLM 响应文本

    Returns:
        最大有效 JSON 块的字符数，无有效 JSON 时返回 0
    """
    best = 0
    for start_char, end_char in (("[", "]"), ("{", "}")):
        pos = 0
        while pos < len(text):
            idx = text.find(start_char, pos)
            if idx == -1:
                break
            depth = 0
            in_string = False
            escaped = False
            end = -1
            for i in range(idx, len(text)):
                ch = text[i]
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == start_char:
                    depth += 1
                elif ch == end_char:
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > idx:
                candidate = text[idx:end]
                try:
                    json.loads(candidate)
                    if len(candidate) > best:
                        best = len(candidate)
                except (json.JSONDecodeError, ValueError):
                    pass
                pos = end
            else:
                pos = idx + 1
    return best


def _check_red_team_format(response: str) -> bool:
    """检查红队响应是否符合预期格式（JSON 数组，每项含 strategy 和 inputs 字段）

    Args:
        response: 红队 LLM 响应文本

    Returns:
        格式有效返回 True，否则返回 False
    """
    candidate = None
    for start_char, end_char in (("[", "]"),):
        idx = response.find(start_char)
        if idx == -1:
            continue
        depth = 0
        in_string = False
        escaped = False
        end = -1
        for i in range(idx, len(response)):
            ch = response[i]
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > idx:
            candidate = response[idx:end]
            break
    if candidate is None:
        return False
    try:
        arr = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(arr, list):
        return False
    return all(
        isinstance(item, dict) and "strategy" in item and "inputs" in item
        for item in arr
    )


_INTENT_PATTERNS: list[re.Pattern] = [
    re.compile(r"I assume you want", re.IGNORECASE),
    re.compile(r"If you mean", re.IGNORECASE),
    re.compile(r"Perhaps you", re.IGNORECASE),
    re.compile(r"It seems like", re.IGNORECASE),
    re.compile(r"I guess you", re.IGNORECASE),
    re.compile(r"Option\s*\d+", re.IGNORECASE),
    re.compile(r"Alternative", re.IGNORECASE),
    re.compile(r"我猜你是想"),
    re.compile(r"你可能想要"),
    re.compile(r"或许你是要"),
    re.compile(r"要么"),
    re.compile(r"或者"),
]


def _check_intent_guessing(response: str) -> bool:
    """检查响应是否包含意图猜测模式（如 "我认为你是想"、"或许你是要" 等）

    先移除所有代码块内容，仅在自然语言部分进行检测。

    Args:
        response: LLM 响应文本

    Returns:
        包含意图猜测模式返回 True，否则返回 False
    """
    text_without_code = re.sub(r"```.*?```", "", response, flags=re.DOTALL)
    for pattern in _INTENT_PATTERNS:
        if pattern.search(text_without_code):
            return True
    return False


class PromptRecorder:
    """LLM 调用链记录器，以 JSONL 格式按日期分文件记录 LLM 交互

    提供记录写入、useful 字段回溯更新、以及格式有效性/代码占比/意图猜测等
    自动指标计算功能。所有文件写入操作均为线程安全。

    Attributes:
        _output_dir: 输出目录路径
        _lock: 线程锁
        _useful_backfill: call_id -> useful 的延迟更新映射
        _context_to_call_ids: (round, caller) -> [call_id] 的索引映射
    """
    def __init__(self, output_dir: str) -> None:
        """初始化记录器，创建输出目录

        Args:
            output_dir: JSONL 文件输出目录路径
        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._useful_backfill: dict[str, bool] = {}
        self._context_to_call_ids: dict[tuple, list[str]] = {}

    def record(self, entry: RecordEntry) -> None:
        """追加一条 LLM 调用记录到当天的 JSONL 文件

        同时更新 _context_to_call_ids 索引，用于后续批量 useful 更新。

        Args:
            entry: 记录条目对象
        """
        file_path = self._output_dir / f"prompt_records_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        try:
            with self._lock:
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
                key = (entry.round, entry.caller)
                if key not in self._context_to_call_ids:
                    self._context_to_call_ids[key] = []
                self._context_to_call_ids[key].append(entry.call_id)
        except OSError:
            _logger.warning("Failed to write record entry to %s", file_path)

    def update_useful(self, call_id: str, useful: bool) -> None:
        """回溯更新指定 call_id 记录的 useful 字段

        读取当天的 JSONL 文件，查找匹配 call_id 的行并更新其 metrics.useful 值，
        然后重写整个文件。同时缓存到 _useful_backfill 映射。

        Args:
            call_id: LLM 调用唯一标识
            useful: 是否有用
        """
        self._useful_backfill[call_id] = useful
        file_path = self._output_dir / f"prompt_records_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        try:
            with self._lock:
                if not file_path.exists():
                    _logger.warning("JSONL file not found for useful update: %s", file_path)
                    return
                lines = file_path.read_text(encoding="utf-8").splitlines()
                updated = False
                new_lines: list[str] = []
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        new_lines.append(line)
                        continue
                    if record.get("call_id") == call_id:
                        metrics = record.get("metrics", {})
                        if isinstance(metrics, dict):
                            metrics["useful"] = useful
                        record["metrics"] = metrics
                        updated = True
                    new_lines.append(json.dumps(record, ensure_ascii=False))
                if updated:
                    file_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                else:
                    _logger.warning("call_id %s not found in JSONL file", call_id)
        except OSError:
            _logger.warning("Failed to update useful for call_id %s", call_id)

    def update_useful_by_context(self, round_num: int | None, caller: str, useful: bool) -> None:
        """按上下文（round + caller）批量更新 useful 字段

        若 round_num 为 None，则匹配所有 round 下对应 caller 的记录。

        Args:
            round_num: 回合编号（可为 None 表示所有回合）
            caller: 调用者类型
            useful: 是否有用
        """
        if round_num is not None:
            key = (round_num, caller)
            call_ids = self._context_to_call_ids.get(key, [])
        else:
            call_ids = []
            for (r, c), ids in self._context_to_call_ids.items():
                if c == caller:
                    call_ids.extend(ids)
        if not call_ids:
            _logger.warning("No records found for round=%s caller=%s", round_num, caller)
            return
        for call_id in call_ids:
            self.update_useful(call_id, useful)

    @staticmethod
    def compute_metrics(response: str, caller: str) -> Metrics:
        """根据响应内容和调用者类型自动计算指标

        包括格式有效性、格式比率（代码/JSON占比）、意图猜测检测。
        不同 caller 类型使用不同的格式验证规则。

        Args:
            response: LLM 响应文本
            caller: 调用者类型（red_team/blue_team/blue_self_iter/constitution_judge）

        Returns:
            填充了 format_valid/format_rate/intent_guessing 字段的 Metrics 对象；
            useful 字段保持 None
        """
        format_valid: bool | None = None
        format_rate: float = 1.0
        total_chars = len(response)

        if caller == CallerType.RED_TEAM.value:
            format_valid = _check_red_team_format(response)
        elif caller in (CallerType.BLUE_TEAM.value, CallerType.BLUE_SELF_ITER.value):
            format_valid = "```" in response
        elif caller == CallerType.CONSTITUTION_JUDGE.value:
            format_valid = "def judge(" in response

        if total_chars > 0:
            code_chars = _extract_code_block_chars(response)
            json_chars = _extract_json_chars(response)
            meaningful = max(code_chars, json_chars)
            if meaningful > 0:
                format_rate = min(meaningful / total_chars, 1.0)

        intent_guessing = _check_intent_guessing(response)

        return Metrics(
            useful=None,
            format_valid=format_valid,
            format_rate=format_rate,
            intent_guessing=intent_guessing,
        )


_prompt_recorder: PromptRecorder | None = None


def get_prompt_recorder(output_dir: str | None = None) -> PromptRecorder | None:
    """获取全局 PromptRecorder 单例

    首次调用时若提供 output_dir 则创建实例，后续调用忽略 output_dir 参数。
    若未提供 output_dir 且尚未初始化，则返回 None。

    Args:
        output_dir: JSONL 文件输出目录路径（仅首次调用时使用）

    Returns:
        PromptRecorder 实例或 None
    """
    global _prompt_recorder
    if output_dir is None:
        return _prompt_recorder
    if _prompt_recorder is None:
        _prompt_recorder = PromptRecorder(output_dir)
    return _prompt_recorder
