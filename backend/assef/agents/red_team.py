"""ASSEF 红队Agent —— 攻击脚本生成器，生成可执行的 Python 攻击脚本探索靶机漏洞"""

from __future__ import annotations

import ast
import re
import json
from typing import Callable

from ..llm import LLMClient
from ..logging_config import get_logger
from ..models import TargetSpec
from ..models import GameRules
from ..models import RoundRecord
from ..core.progress import ProgressEvent


_logger = get_logger("red_team")


RED_TEAM_SYSTEM_PROMPT = """\
You are a red-team security researcher. Your task is to write a Python attack script that exploits vulnerabilities in a target system.

## What You Generate
A complete, executable Python program that:
1. Reads a JSON input from stdin (json.loads(sys.stdin.read()))
2. Calls the target's public functions directly with crafted malicious inputs
3. Tries multiple attack vectors in sequence
4. Prints results to stdout for each attack attempt
5. If an attack succeeds, prints the full output and exits

## Attack Vectors to Explore
- **Illegal values**: None, empty strings, very long strings, negative numbers, wrong types
- **Boundary attacks**: Extremely large/small numeric values, edge cases, overflow candidates
- **Injection attacks**: Special characters, SQL-like syntax, command injection patterns, format string attacks
- **Logic bypass**: Reserved words, internal parameters, admin/root/superuser keys, boolean trickery
- **Encoding attacks**: Unicode trickery, escape sequences, obfuscation, encoding confusion
- **Type confusion**: Sending strings where numbers expected, arrays where objects expected, etc.

## Execution Environment (Sandbox)
- Your script is **appended to the target code** and both run together in a single process sandbox
- The target's public functions are defined **inline in the same file** — call them directly (e.g., `query_user("alice")`)
- NO import statements needed for the target — the functions are already in scope
- stdin receives the input JSON that would normally be sent to the target
- stdout is captured for judging — print your findings clearly
- Dangerous patterns (file operations, network calls, subprocess spawning) are BLOCKED
- Your script should NOT attempt to escape the sandbox — focus on exploiting the target logic

## Rules
1. Write ONLY the Python code — no markdown, no explanations, no code fences
2. The script MUST be syntactically valid and executable
3. Do NOT import the target module — its functions are in the same file scope
4. Use `if __name__ == "__main__":` pattern to read stdin and call target functions
5. Be creative and try diverse attack vectors within a single script
6. Keep the script focused and efficient — the sandbox has a time limit
"""


SYS_SANDBOX_DESC = """\
## Sandbox Execution Environment
- **Execution model**: The target code and your attack script are concatenated and run together as one file
- **Target functions**: Already defined in the same file scope — call them directly (e.g., `query_user("alice")`)
- **Timeout**: The script has a strict execution time limit
- **Available stdlib modules**: json, sys, os.path, math, re, random, itertools, collections, datetime, copy, functools
- **Dangerous patterns BLOCKED**: file I/O (open, read, write), network (socket, http, urllib), subprocess (os.system, subprocess, exec, eval), code execution
- **Input format**: Your script receives input via `json.loads(sys.stdin.read())` — this is the same JSON format that normal_tests use
- **Output**: Print results to stdout — it will be captured and judged
"""


def _summarize_defense(record: RoundRecord, original_code_length: int | None = None) -> str:
    """生成蓝队防御代码的摘要描述

    Args:
        record: 当前回合记录（含防御代码）
        original_code_length: 原始代码行数，用于计算行数变化（可选）

    Returns:
        str: 防御代码的行数和相对原始代码的变化信息
    """
    if record.defense_code is None:
        return "No defense submitted"
    defense_lines = len(record.defense_code.splitlines())
    if original_code_length is not None:
        diff = defense_lines - original_code_length
        sign = "+" if diff >= 0 else ""
        return f"Blue team submitted defense code ({defense_lines} lines, {sign}{diff} from original)"
    return f"Blue team submitted defense code ({defense_lines} lines)"


def _build_attack_prompt(
    target: TargetSpec,
    history: list[RoundRecord] | None,
    rules: GameRules,
    round_num: int,
    defense_code: str = "",
) -> list[dict]:
    """构建红队攻击脚本生成的 LLM 对话消息

    根据靶机信息、历史对抗记录和当前防御代码组装 system/user 消息，
    引导 LLM 生成有针对性的攻击脚本。

    Args:
        target: 靶机规格（含公共接口、正常测试用例）
        history: 历史对抗记录列表（可选，提供攻击成功/失败的上下文）
        rules: 游戏规则（含最大回合数等配置）
        round_num: 当前回合编号
        defense_code: 蓝队当前防御代码（可选，供红队分析）

    Returns:
        list[dict]: 包含 system 和 user 角色的对话消息列表
    """
    blood_bank_count = sum(1 for r in (history or []) if r.attack_success)
    defense_count = sum(1 for r in (history or []) if r.defense_code is not None)

    normal_tests_str = json.dumps(
        [{"name": t.name, "input": t.input, "expected_output": t.expected_output} for t in target.normal_tests],
        indent=2,
        ensure_ascii=False,
    )

    user_content = f"""\
## Round {round_num} of {rules.max_arena_rounds}. Blood bank has {blood_bank_count} attacks. Blue has defended {defense_count} times.

## Target Information
- Name: {target.name}
- Description: {target.description}
- Public Interface:
{target.public_spec}

## Normal Tests (for understanding expected behavior)
{normal_tests_str}

## Instructions
Write a Python attack script that tries multiple attack vectors against this target.
The target's functions are in the same file scope — call them directly (e.g., `query_user(username)`).
Read input via `json.loads(sys.stdin.read())` to get the test parameters.
Try different payloads for each attack vector. Print the results of each attempt.
{SYS_SANDBOX_DESC}
"""

    if history:
        user_content += "\n\n## Full History:\n"
        for record in history:
            status = "SUCCESS" if record.attack_success else "BLOCKED"
            user_content += f"\nRound {record.round_num}: {status}\n"
            if record.attack_script:
                user_content += f"  Attack Script: {record.attack_script[:300]}{'...' if len(record.attack_script) > 300 else ''}\n"
            user_content += f"  Output: {record.attack_output[:300]}\n"
            user_content += f"  Defense: {_summarize_defense(record)}\n"

    if defense_code:
        original_lines = len(target.code.splitlines())
        current_lines = len(defense_code.splitlines())
        diff = current_lines - original_lines
        sign = "+" if diff >= 0 else ""
        user_content += f"\n\n## Current Defense Code Status\n"
        user_content += f"Original code: {original_lines} lines. Current defense: {current_lines} lines ({sign}{diff}).\n"

    user_content += "\nWrite your attack script now:"

    return [
        {"role": "system", "content": RED_TEAM_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _extract_attack_script(response: str) -> str:
    """从 LLM 原始响应中提取攻击脚本代码

    兼容 reasoning model（如 deepseek）在响应中混合推理文本和代码的情况。
    按优先级：
    1. 取最后一个 ```python 代码块
    2. 取最后一个 ``` 代码块（无语言标记）
    3. 从 "import" 或 "def " 行开始提取到末尾

    Args:
        response: LLM 的原始文本响应

    Returns:
        str: 提取出的 Python 攻击脚本源代码
    """
    # 策略 1-2: markdown 代码块，取最后一个
    for pat in [r"```python\s*\n(.*?)```", r"```(?:python)?\s*\n(.*?)```", r"```(?:python)?\s*(.*?)```"]:
        matches = list(re.finditer(pat, response, re.DOTALL))
        if matches:
            code = matches[-1].group(1).strip()
            if code and ("import " in code or "def " in code or "print(" in code or "sys." in code):
                return code

    # 策略 3: 从有用代码行开始提取
    for marker in ["import json", "import sys", "def main(", "def attack(", "if __name__"]:
        pos = response.find(marker)
        if pos >= 0:
            extracted = response[pos:].strip()
            # 截断到下一个 ``` 标记
            end = extracted.find("\n```")
            if end > 0:
                extracted = extracted[:end].strip()
            return extracted

    return response.strip()


def _validate_python_syntax(script: str) -> bool:
    try:
        compile(script, "<attack_script>", "exec")
        return True
    except SyntaxError as e:
        _logger.warning("Python syntax validation failed: %s\nScript (first 500 chars): %.500s", e, script)
        return False


class RedTeamAgent:
    """红队攻击代理 —— 通过 LLM 生成可执行的 Python 攻击脚本"""

    def __init__(self, llm_client: LLMClient, rules: GameRules | None = None) -> None:
        self._llm = llm_client
        self._rules = rules or GameRules()

    def generate_attack(
        self,
        target: TargetSpec,
        history: list[RoundRecord] | None = None,
        on_progress: Callable[[ProgressEvent], None] | None = None,
        pause_event=None,
        on_llm_progress: Callable[[str, str, int], None] | None = None,
    ) -> str:
        """生成下一轮攻击脚本

        根据靶机信息、历史对抗结果，通过 LLM 生成一个可执行的 Python 攻击脚本。

        Args:
            target: 靶机规格描述
            history: 历史对抗记录（可选，用于提供上下文）

        Returns:
            str: Python 攻击脚本源代码
        """
        round_num = len(history) + 1 if history else 1

        if on_progress is not None:
            on_progress(ProgressEvent(type="step_start", role="red_team", step_name="generate_attack", data={"rounds_history_len": len(history) if history else 0}))

        _logger.debug(
            "generate_attack(): target=%s, round_num=%d",
            target.name, round_num,
        )

        defense_code = ""
        if history:
            for record in reversed(history):
                if record.defense_code:
                    defense_code = record.defense_code
                    break

        messages = _build_attack_prompt(
            target, history, self._rules,
            round_num, defense_code,
        )
        _logger.debug(
            "generate_attack(): calling LLM, message_chars=%d",
            sum(len(m.get("content", "")) for m in messages),
        )
        if pause_event is not None:
            pause_event.wait()
        self._llm.set_call_context({
            "caller": "red_team",
            "round": round_num,
        })
        if on_llm_progress is not None:
            cum_chars = [0]
            def _on_phase(phase):
                on_llm_progress(phase, "", cum_chars[0])
            def _on_token(token, phase):
                cum_chars[0] += len(token)
                on_llm_progress(phase, token, cum_chars[0])
            response = self._llm.chat_stream_with_phase(messages, _on_phase, _on_token, temperature=0.8, max_tokens=8192)
        else:
            response = self._llm.chat(messages, temperature=0.8, max_tokens=8192)
        _logger.info("红队 LLM 响应: round=%d, response_len=%d, response=%.1000s", round_num, len(response), response)
        script = _extract_attack_script(response)
        if script and not _validate_python_syntax(script):
            _logger.error("Red team attack script failed syntax validation")
            script = ""
        _logger.info("红队攻击脚本: target=%s round=%d script_len=%d",
            target.name, round_num, len(script))
        if on_progress is not None:
            on_progress(ProgressEvent(
                type="step_done",
                role="red_team",
                step_name="generate_attack",
                content=script[:2000],
                data={"round": round_num, "script_length": len(script), "raw_response": response[:2000]},
            ))
        _logger.debug(
            "generate_attack(): LLM response, response_len=%d, script_len=%d",
            len(response), len(script),
        )

        return script
