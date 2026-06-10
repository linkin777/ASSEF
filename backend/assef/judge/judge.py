"""ASSEF 判官模块 —— 沙箱执行与代码判定，负责在隔离环境中执行代码并评估结果"""

import json
import os
import subprocess
import sys
import tempfile
import time

from ..logging_config import get_logger
from ..models.results import VerdictDetail, VerdictReport
from ..models.target_spec import TargetSpec


_logger = get_logger("judge")


def _execute_in_sandbox(code: str, input_data: dict, timeout: float = 30.0) -> tuple[str, str, int, bool, float]:
    """在隔离沙箱中执行 Python 代码并返回执行结果

    将代码写入临时文件，通过子进程运行，以 JSON 形式传入输入数据并捕获输出。
    内置危险模式检测，阻止 os.system、subprocess、文件操作、网络调用等。

    Args:
        code: 待执行的 Python 源代码
        input_data: 通过 stdin 传入代码的 JSON 输入数据
        timeout: 子进程超时时间（秒），默认 30.0

    Returns:
        tuple[str, str, int, bool, float]: 包含以下元素的元组：
            - stdout (str): 标准输出内容
            - stderr (str): 标准错误内容（含超时等异常信息）
            - exit_code (int): 进程退出码（-1 表示被阻止或异常）
            - timed_out (bool): 是否超时
            - elapsed (float): 实际执行耗时（秒）

    Raises:
        不抛出异常 —— 所有错误均通过返回值中的 exit_code=-1 和 stderr 字段返回
    """
    DANGEROUS = ["os.system", "subprocess", "__import__", "eval(", "exec(", "open(",
                 "import socket", "import http", "import urllib", "import ftplib", "import requests"]
    code_lower = code.lower()
    for pattern in DANGEROUS:
        if pattern in code_lower:
            _logger.debug("Sandbox execution blocked: code_len=%d, input_keys=%s, dangerous_pattern=%s",
                          len(code), list(input_data.keys()), pattern)
            return ("", f"SecurityError: dangerous operation detected: {pattern}", -1, False, 0.0)

    _logger.debug("Sandbox executing: code_len=%d, input_keys=%s", len(code), list(input_data.keys()))
    fd, temp_path = tempfile.mkstemp(suffix=".py")
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(code)

        start = time.perf_counter()
        result = subprocess.run(
            [sys.executable, temp_path],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        elapsed = time.perf_counter() - start
        _logger.debug("Sandbox done: elapsed=%.4fs, exit_code=%d, timed_out=%s", elapsed, result.returncode, False)
        return (result.stdout.strip(), result.stderr.strip(), result.returncode, False, elapsed)
    except subprocess.TimeoutExpired as te:
        elapsed = time.perf_counter() - start
        partial_stdout = te.stdout.decode("utf-8", errors="replace") if te.stdout else ""
        partial_stderr = te.stderr.decode("utf-8", errors="replace") if te.stderr else ""
        rich_stderr = f"TimeoutExpired: execution exceeded {timeout}s"
        if partial_stderr:
            rich_stderr += f"\n--- partial stderr ---\n{partial_stderr}"
        _logger.debug("Sandbox timeout: elapsed=%.4fs, exit_code=%d, timed_out=%s", elapsed, -1, True)
        return (partial_stdout, rich_stderr, -1, True, elapsed)
    except Exception as e:
        _logger.error("Sandbox exception: %s", e, exc_info=True)
        return ("", str(e), -1, False, 0.0)
    finally:
        os.unlink(temp_path)


class Judge:
    """代码判官 —— 在隔离沙箱中执行代码并判定正常/攻击测试的结果"""

    def __init__(self) -> None:
        pass

    def judge_normal(self, target: TargetSpec, code: str) -> VerdictReport:
        """对代码执行所有正常功能测试，逐一比对期望输出与实际输出

        Args:
            target: 靶机规格（包含正常测试用例列表）
            code: 待判定的 Python 代码

        Returns:
            VerdictReport: 汇总判定结果，attack_success 字段恒为 False
        """
        _logger.debug("judge_normal started: total_tests=%d", len(target.normal_tests))
        details: list[VerdictDetail] = []
        for test in target.normal_tests:
            stdout, stderr, exit_code, timed_out, _elapsed = _execute_in_sandbox(code, test.input)

            error: str | None = None
            passed = False

            if timed_out:
                error = "TimeoutExpired"
            elif exit_code != 0:
                error = stderr if stderr else f"Exit code: {exit_code}"
            else:
                try:
                    actual = json.loads(stdout) if stdout else None
                except json.JSONDecodeError:
                    error = f"stdout is not valid JSON: {stdout}"
                else:
                    if actual == test.expected_output:
                        passed = True
                    else:
                        error = f"Output mismatch. Expected: {json.dumps(test.expected_output)}, Got: {stdout}"

            _logger.info("judge_normal test: test_name=%s, exit_code=%d, passed=%s, error=%s",
                          test.name, exit_code, passed, error)

            detail = VerdictDetail(
                test_name=test.name,
                input=test.input,
                expected_output=json.dumps(test.expected_output),
                actual_output=stdout,
                passed=passed,
                error=error,
            )
            details.append(detail)

        passed_count = sum(1 for d in details if d.passed)
        failed_count = len(details) - passed_count
        _logger.info("judge_normal finished: passed=%d, failed=%d", passed_count, failed_count)

        return VerdictReport(
            total_tests=len(details),
            passed=passed_count,
            failed=failed_count,
            attack_success=False,
            details=details,
        )

    def judge_attack(self, target: TargetSpec, code: str, attack_inputs: list[dict]) -> VerdictReport:
        """对代码执行攻击测试，检查输出是否包含攻击成功关键字

        Args:
            target: 靶机规格（包含攻击成功条件）
            code: 待判定的 Python 代码
            attack_inputs: 攻击输入列表

        Returns:
            VerdictReport: 汇总判定结果，attack_success 为是否存在任一攻击通过
        """
        _logger.debug("judge_attack started: total_attack_inputs=%d", len(attack_inputs))
        details: list[VerdictDetail] = []
        attack_keywords = target.success_criteria.attack

        for i, attack_input in enumerate(attack_inputs):
            stdout, stderr, exit_code, timed_out, _elapsed = _execute_in_sandbox(code, attack_input)

            error: str | None = None
            passed = False

            if timed_out:
                error = "TimeoutExpired"
            elif exit_code != 0:
                error = stderr if stderr else f"Exit code: {exit_code}"
            else:
                if attack_keywords in stdout:
                    passed = True
                else:
                    error = f"Attack criteria not met. Expected keyword '{attack_keywords}' not found in output."

            _logger.info("judge_attack test: test_name=attack_%d, exit_code=%d, passed=%s, error=%s",
                          i, exit_code, passed, error)

            detail = VerdictDetail(
                test_name=f"attack_{i}",
                input=attack_input,
                expected_output=None,
                actual_output=stdout,
                passed=passed,
                error=error,
            )
            details.append(detail)

        passed_count = sum(1 for d in details if d.passed)
        failed_count = len(details) - passed_count
        attack_success = any(d.passed for d in details)
        _logger.info("judge_attack finished: passed=%d, failed=%d, attack_success=%s",
                     passed_count, failed_count, attack_success)

        return VerdictReport(
            total_tests=len(details),
            passed=passed_count,
            failed=failed_count,
            attack_success=attack_success,
            details=details,
        )

    def execute_judge_script(self, script: str, code: str, inputs: list[dict], original_code_len: int = 0, new_code_len: int = 0) -> VerdictReport:
        """通过动态生成的判官函数对代码执行自定义判定

        先在沙箱中执行代码获取各测试的实际输出，再将所有执行结果传入由 LLM 生成的
        `judge(inputs: list[dict], original_code_len: int, new_code_len: int) -> dict` 函数进行最终判定。

        Args:
            script: LLM 生成的纯 Python judge 函数源码
            code: 待判定的 Python 代码
            inputs: 测试输入列表，每个元素包含 name/input/expected_output 键
            original_code_len: 原始代码行数（蓝队评估用）
            new_code_len: 新代码行数（蓝队评估用）

        Returns:
            VerdictReport: 汇总判定结果
        """
        _logger.debug("execute_judge_script started: inputs_count=%d, script_len=%d", len(inputs), len(script))
        DANGEROUS = ["os.system", "subprocess", "__import__", "eval(", "exec(", "open(",
                     "import socket", "import http", "import urllib", "import ftplib", "import requests"]
        script_lower = script.lower()
        for pattern in DANGEROUS:
            if pattern in script_lower:
                _logger.warning("execute_judge_script security violation: dangerous_pattern=%s", pattern)
                return VerdictReport(
                    total_tests=0,
                    passed=0,
                    failed=0,
                    attack_success=False,
                    details=[VerdictDetail(
                        test_name="security",
                        input={},
                        expected_output=None,
                        actual_output="",
                        passed=False,
                        error=f"Judge script contains dangerous pattern: {pattern}",
                    )],
                )

        execution_results: list[dict] = []
        for inp in inputs:
            stdout, stderr, exit_code, timed_out, elapsed = _execute_in_sandbox(code, inp.get("input", {}))
            _logger.info("沙箱执行[%s]: elapsed=%.3fs exit_code=%d stdout_len=%d stderr_len=%d",
                inp.get("name", "unknown"), elapsed, exit_code, len(stdout), len(stderr))
            execution_results.append({
                "name": inp.get("name", "unknown"),
                "input": inp.get("input", {}),
                "expected_output": json.dumps(inp.get("expected_output")) if inp.get("expected_output") is not None else None,
                "actual_output": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "elapsed_time": elapsed,
            })

        # ── Fallback 判定函数（当 LLM 生成的判词脚本失败时使用） ──
        def _fallback_judge(exec_results: list[dict], _orig_len: int = 0, _new_len: int = 0) -> dict:
            """内置启发式判定：当 LLM 判词脚本执行出错时的安全兜底"""
            results = []
            for er in exec_results:
                name = er.get("name", "unknown")
                expected_str = er.get("expected_output")
                actual_str = er.get("actual_output", "")
                is_attack = expected_str is None
                if is_attack:
                    has_flag = "flag{" in actual_str.lower()
                    results.append({
                        "name": name, "passed": not has_flag,
                        "reason": "Attack leaked flag" if has_flag else "Attack blocked (no flag detected)",
                    })
                else:
                    try:
                        expected_obj = _json.loads(expected_str) if isinstance(expected_str, str) else expected_str
                        actual_obj = _json.loads(actual_str) if isinstance(actual_str, str) else actual_str
                        passed = expected_obj == actual_obj
                        reason = "Output matches expected" if passed else f"Output mismatch"
                    except Exception:
                        passed, reason = False, f"Cannot parse: {actual_str[:80]}"
                    results.append({"name": name, "passed": passed, "reason": reason})
            attack_tests = [r for r in results if r["name"].startswith("attack_")]
            normal_tests = [r for r in results if not r["name"].startswith("attack_")]
            attack_success = any(not r["passed"] for r in attack_tests)
            normal_all_passed = all(r["passed"] for r in normal_tests) if normal_tests else True
            all_attacks_blocked = all(r["passed"] for r in attack_tests) if attack_tests else True
            defense_passed = normal_all_passed and all_attacks_blocked
            bloat = max(0, (_new_len - _orig_len) / max(_orig_len, 1))
            cost_score = round(max(0.1, 0.5 - min(0.3, bloat * 0.15)), 3)
            return {"attack_success": attack_success, "defense_passed": defense_passed, "results": results, "cost_score": cost_score}

        import json as _json, re as _re
        from typing import Optional as _Optional
        local_env: dict = {}
        exec_failed = False
        try:
            exec(script, {"__builtins__": __builtins__, "json": _json, "re": _re, "Optional": _Optional}, local_env)
            _logger.debug("execute_judge_script exec succeeded")
        except Exception as e:
            _logger.error("execute_judge_script exec failed: %s — using fallback", e)
            exec_failed = True

        judge_func = local_env.get("judge") if not exec_failed else None
        if judge_func is None and not exec_failed:
            _logger.warning("execute_judge_script: no 'judge' function found — using fallback")

        if judge_func is None:
            _logger.info("execute_judge_script: using fallback judge (no valid judge_func)")
            result = _fallback_judge(execution_results, original_code_len, new_code_len)
        else:
            try:
                result = judge_func(execution_results, original_code_len, new_code_len)
                _logger.debug("execute_judge_script judge_func executed successfully")
            except TypeError:
                _logger.info("judge_func does not accept code_len params, falling back to old signature")
                try:
                    result = judge_func(execution_results)
                except Exception as e:
                    _logger.error("execute_judge_script judge_func execution error (old sig): %s — using fallback", e)
                    result = _fallback_judge(execution_results, original_code_len, new_code_len)
            except Exception as e:
                _logger.error("execute_judge_script judge_func execution error: %s — using fallback", e)
                result = _fallback_judge(execution_results, original_code_len, new_code_len)

        if result is None:
            _logger.warning("execute_judge_script judge_func returned None — using fallback")
            result = _fallback_judge(execution_results, original_code_len, new_code_len)

        attack_success = result.get("attack_success", False)
        defense_passed = result.get("defense_passed", False)
        cost_score = result.get("cost_score", 0.0)
        # 结果列表中仅保留正常测试和攻击测试（即排除执行错误时期的占位条目）
        details: list[VerdictDetail] = []
        for r in result.get("results", []):
            detail = VerdictDetail(
                test_name=r.get("name", "unknown"),
                input=r.get("input", {}),
                expected_output=r.get("expected_output"),
                actual_output=r.get("actual_output", ""),
                passed=r.get("passed", False),
                error=r.get("reason") if not r.get("passed") else None,
            )
            details.append(detail)
            _logger.info("判定测试: test_name=%s passed=%s input=%s expected=%s actual=%s reason=%s",
                detail.test_name, detail.passed,
                str(detail.input)[:100], str(detail.expected_output)[:100],
                str(detail.actual_output)[:100], detail.error or "OK")

        passed_count = sum(1 for d in details if d.passed)
        failed_count = len(details) - passed_count
        _logger.info("execute_judge_script finished: passed=%d, failed=%d, attack_success=%s, defense_passed=%s, cost_score=%.3f",
                     passed_count, failed_count, attack_success, defense_passed, cost_score)
        return VerdictReport(
            total_tests=len(details),
            passed=passed_count,
            failed=failed_count,
            attack_success=attack_success,
            defense_passed=defense_passed,
            cost_score=cost_score,
            details=details,
        )
