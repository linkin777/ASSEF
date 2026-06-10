"""ASSEF 宪法Agent —— 将宪法规则翻译为可执行的判官脚本"""

from __future__ import annotations

import ast
import re

from typing import Callable

from ..llm import LLMClient
from ..logging_config import get_logger
from ..models import Constitution
from ..models.target_spec import TargetSpec

_logger = get_logger("constitution_agent")

MAX_GENERATION_RETRIES = 3
RETRY_PROMPT_SUFFIX = """

IMPORTANT: Your previous response was rejected because it either contained blocked keywords (os.system, subprocess, __import__, eval, exec, open, socket, http, urllib, ftplib, requests, os, sys) in the response text, or was missing a valid "def judge(" function definition.

CRITICAL RULES:
1. Output ONLY the Python function code inside ```python ... ``` markdown fence, with NO explanatory text outside the code block.
2. Do NOT mention any blocked keywords anywhere in your response (including in comments or docstrings).
3. The function MUST be named "judge" with signature: def judge(inputs, original_code_len=0, new_code_len=0):
"""

DANGEROUS_PATTERNS = [
    "os.system", "subprocess", "__import__", "eval(", "exec(", "open(",
    "import socket", "import http", "import urllib", "import ftplib", "import requests",
    "import os", "import sys",
]


JUDGE_SCRIPT_SYSTEM_PROMPT = """\
You are a constitutional judge script generator. Your job is to translate high-level constitutional rules into an executable Python function for judging red-team attacks and blue-team fixes.

## Sandbox Environment Context
The code under judgment runs in an isolated sandbox with these characteristics:
- Python subprocess sandbox with configurable timeout
- stdin receives JSON input, stdout is captured as text
- Certain dangerous patterns are blocked at the sandbox level: os.system, subprocess, __import__, eval, exec, open, socket, http, urllib, ftplib, requests, os, sys imports
- Only pure Python builtins are available in the sandbox; no external libraries
- Each test execution produces: stdout, stderr, exit_code, timed_out flag, elapsed_time in seconds

## Output Format
Return ONLY a Python function named `judge` with this exact signature:

def judge(inputs: list[dict], original_code_len: int = 0, new_code_len: int = 0) -> dict:
    ...

Each input dict has these keys:
- name (str): the test/attack name
- input (dict): the input JSON sent to the sandbox
- expected_output (str or None): expected JSON output for normal tests; None for attack tests
- actual_output (str): the actual stdout captured from sandbox execution
- stderr (str): stderr captured from sandbox
- exit_code (int): process exit code (0 = success)
- timed_out (bool): whether execution timed out
- elapsed_time (float): execution wall time in seconds

Parameters:
- original_code_len: line count of the original vulnerable code (0 when judging attack only)
- new_code_len: line count of the blue team's defense code (0 when judging attack only)

Return format:
{
    "attack_success": bool,   # True if at least one attack succeeded (vulnerability confirmed)
    "defense_passed": bool,   # True if all normal tests pass AND all attacks are blocked
    "results": [
        {
            "name": str,
            "passed": bool,
            "reason": str  # explanation, keep under 200 chars
        }
    ],
    "cost_score": float,  # 0.0-1.0, derived from constitution scoring_rules
}

### cost_score Calculation
The cost_score measures the efficiency of the blue team's defense. It should be derived from the constitution's scoring_rules formula. Typical factors:
- Code bloat: (new_code_len - original_code_len) / max(original_code_len, 1), lower is better
- Performance: average elapsed_time of normal tests vs expected baseline, lower is better
- Readability: inferred from stderr presence, excessive exit_code!=0, or timeout occurrences, fewer issues is better

When judging attack-only scenarios (no blue team code), set cost_score to 0.0.
When original_code_len and new_code_len are both 0, treat it as attack-only judging.

## Rules
1. Use ONLY builtin modules: json, re, str, dict, list, bool, int, float, len, sum, min, max, abs, round, etc.
2. NO import statements at all (use only builtins).
3. Pure function, no side effects, no file/network access.
4. The function must be self-contained and complete.
5. Return valid Python dict as specified above.
6. **CRITICAL**: Output ONLY the Python code. Do NOT include any explanatory text, reasoning, analysis, or markdown outside the code. Start directly with ```python and end with ```. No "Here is the code" or similar text.

Now generate the judge function based on the constitution and target context below.
"""


def _build_judge_prompt(constitution: Constitution, target: TargetSpec, sandbox_description: str = "") -> list[dict]:
    sandbox_section = ""
    if sandbox_description:
        sandbox_section = f"""
## Sandbox Environment
{sandbox_description}

### Important Notes
- The sandbox blocks dangerous patterns: os.system, subprocess, __import__, eval, exec, open, socket, http, urllib, ftplib, requests, os, sys
- Each test result includes elapsed_time for performance-based cost evaluation
- Code that times out or produces stderr should be penalized in cost_score
"""

    user_content = f"""\
## Constitution
### Preamble
{constitution.preamble}

### Attack Success Criteria
{constitution.attack_success_criteria}

### Fix Success Criteria
{constitution.fix_success_criteria}

### Scoring Rules (for cost_score computation)
{constitution.scoring_rules}

### Technical Constraints
{constitution.constraints}
{sandbox_section}
## Target Context
### Name: {target.name}
### Description: {target.description}
### Attack Surface: {target.attack_surface}
### Public Interface: {target.public_spec}
### Success Criteria for this target:
- Attack: {target.success_criteria.attack}
- Fix: {target.success_criteria.fix}

### Normal Tests:
"""
    for t in target.normal_tests:
        user_content += f"- {t.name}: input={t.input}, expected={t.expected_output}\n"

    return [
        {"role": "system", "content": JUDGE_SCRIPT_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _extract_function(response: str) -> str:
    """从 LLM 原始响应中提取 judge 函数代码

    按优先级尝试多种提取策略：
    1. 标准 markdown 代码块 (```python ... ```)
    2. 非标准 markdown 代码块 (``` ... ``` 无语言标记)
    3. 查找最后一个 ```python 块（reasoning model 可能在前面有推理文本）
    4. 从 "def judge(" 位置开始，按缩进提取完整函数体

    Args:
        response: LLM 的原始文本响应

    Returns:
        str: 提取出的纯 Python 函数源代码
    """
    # 策略 1-2: 标准 markdown 代码块
    for pat in [r"```(?:python)?\s*\n(.*?)```", r"```(?:python)?\s*(.*?)```"]:
        matches = list(re.finditer(pat, response, re.DOTALL))
        if matches:
            # 取最后一个匹配（reasoning model 可能在前面有 junk）
            code = matches[-1].group(1).strip()
            if code:
                return _extract_function_body(code)

    # 策略 3: 查找 ```python 块，取最后一个
    python_blocks = list(re.finditer(r"```python\s*(.*?)```", response, re.DOTALL))
    if python_blocks:
        code = python_blocks[-1].group(1).strip()
        if code:
            return _extract_function_body(code)

    # 策略 4: 从 "def judge(" 位置提取函数体
    judge_pos = response.find("def judge(")
    if judge_pos >= 0:
        return _extract_function_body(response[judge_pos:])

    return response.strip()


def _extract_function_body(text: str) -> str:
    """从文本中提取 def judge(...) 函数体

    基于 Python 缩进规则，从 "def judge(" 开始提取完整的函数定义。
    兼容 reasoning model 响应中可能包含的额外解释文本。

    Args:
        text: 包含 judge 函数定义的文本片段

    Returns:
        str: 纯函数体代码
    """
    lines = text.splitlines()
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("def judge("):
            start_idx = i
            break

    if start_idx is None:
        return text.strip()

    # 获取函数定义的缩进级别
    start_line = lines[start_idx]
    base_indent = len(start_line) - len(start_line.lstrip())

    # 提取函数体：包含从 def judge( 开始，到缩进回到 base_indent 级别且非空行
    result_lines = []
    in_function = False
    for i in range(start_idx, len(lines)):
        line = lines[i]
        stripped = line.strip()

        if i == start_idx:
            result_lines.append(line)
            in_function = True
            continue

        if not stripped:
            # 空行保留（函数体内部的分隔）
            if in_function:
                result_lines.append(line)
            continue

        line_indent = len(line) - len(line.lstrip())

        if in_function:
            # 如果缩进回到 base_indent 或更小且不是注释/装饰器，函数结束
            if line_indent <= base_indent and not stripped.startswith("@") and not stripped.startswith("#"):
                break
            result_lines.append(line)

    return "\n".join(result_lines).strip()


def _strip_comments(script: str) -> str:
    """移除脚本中的所有注释（多行文档字符串和单行 # 注释）

    用于安全检查前的代码清理，防止危险模式隐藏在注释中。

    Args:
        script: 原始 Python 脚本源代码

    Returns:
        str: 移除注释后的纯代码文本
    """
    import re
    code_lower = script.lower()
    code_lower = re.sub(r'""".*?"""', '', code_lower, flags=re.DOTALL)
    code_lower = re.sub(r"'''.*?'''", '', code_lower, flags=re.DOTALL)
    result_lines = []
    for line in code_lower.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "#" in line:
            line = line[:line.index("#")]
        result_lines.append(line)
    return "\n".join(result_lines)


def _validate_script(script: str) -> bool:
    """校验生成的判官脚本是否安全、语法正确且包含 judge 函数

    移除注释后检查危险模式，通过 compile() 校验 Python 语法，
    并确认代码定义了 judge 函数。

    Args:
        script: 待校验的 Python 脚本源代码

    Returns:
        bool: True 表示脚本通过所有校验
    """
    code_only = _strip_comments(script)
    for pattern in DANGEROUS_PATTERNS:
        if pattern in code_only:
            _logger.debug("Script validation failed: dangerous_pattern=%s", pattern)
            return False
    try:
        compile(script, "<judge_script>", "exec")
    except SyntaxError as e:
        _logger.warning("Script validation failed: syntax error: %s", e)
        _logger.debug("Script with syntax error (first 500 chars): %.500s", script)
        return False
    has_judge = "def judge(" in script
    _logger.debug("Script validation result: %s", has_judge)
    return has_judge


class ConstitutionAgent:
    """宪法判官脚本生成器 —— 基于宪法规则和靶机上下文，通过 LLM 生成 judge 函数"""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def generate_judge_script(self, constitution: Constitution, target: TargetSpec, sandbox_description: str = "", on_llm_progress: Callable[[str, str, int], None] | None = None) -> str:
        """根据宪法和目标生成可执行判官脚本（带自动重试）

        Args:
            constitution: ASSEF 裁判宪法规则
            target: 靶机规格描述
            sandbox_description: 沙箱环境描述文本（超时时间、危险模式等）

        Returns:
            str: 纯 Python 的 judge 函数源码

        Raises:
            ValueError: 若多次重试后生成的脚本仍未通过安全校验
        """
        messages = _build_judge_prompt(constitution, target, sandbox_description)
        prompt_len = sum(len(m.get("content", "")) for m in messages)
        _logger.debug("Calling LLM for judge script generation: prompt_len=%d", prompt_len)

        last_error = None
        for attempt in range(MAX_GENERATION_RETRIES):
            if on_llm_progress is not None:
                cum_chars = [0]
                def _on_phase(phase):
                    on_llm_progress(phase, "", cum_chars[0])
                def _on_token(token, phase):
                    cum_chars[0] += len(token)
                    on_llm_progress(phase, token, cum_chars[0])
                response = self._llm.chat_stream_with_phase(messages.copy(), _on_phase, _on_token, temperature=0.2, max_tokens=4096)
            else:
                response = self._llm.chat(messages, temperature=0.2, max_tokens=4096)
            _logger.debug("LLM response received (attempt %d/%d): response_len=%d",
                         attempt + 1, MAX_GENERATION_RETRIES, len(response))

            if not response or not response.strip():
                _logger.warning("LLM returned empty response (attempt %d/%d)", attempt + 1, MAX_GENERATION_RETRIES)
                if attempt < MAX_GENERATION_RETRIES - 1:
                    continue
                raise ValueError("Generated judge script failed validation: LLM returned empty response after all retries")

            script = _extract_function(response)
            if not script or not script.strip():
                _logger.warning("Extracted empty script from LLM response (attempt %d/%d)", attempt + 1, MAX_GENERATION_RETRIES)
                if attempt < MAX_GENERATION_RETRIES - 1:
                    messages.append({"role": "user", "content": RETRY_PROMPT_SUFFIX})
                    continue
                raise ValueError("Generated judge script failed validation: extracted empty script after all retries")

            if _validate_script(script):
                _logger.info("Generated judge script passed validation (attempt %d/%d)", attempt + 1, MAX_GENERATION_RETRIES)
                _logger.info("判官脚本已生成: script_chars=%d", len(script))
                _logger.debug("判官脚本完整代码:\n%s", script)
                return script

            _logger.warning("Generated judge script failed validation (attempt %d/%d)", attempt + 1, MAX_GENERATION_RETRIES)
            last_error = "Generated judge script failed validation"

            if attempt < MAX_GENERATION_RETRIES - 1:
                messages.append({"role": "user", "content": RETRY_PROMPT_SUFFIX})

        raise ValueError(last_error or "Generated judge script failed validation")
