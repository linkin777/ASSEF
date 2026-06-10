"""ASSEF 模式B评测引擎 —— 多模型代码修复能力排行榜"""

from __future__ import annotations

import time

from ..logging_config import get_logger
from ..agents import BlueTeamAgent
from ..judge import Judge
from ..models import TargetSpec
from ..llm import LLMClient
from ..models import ModelScore, BenchmarkResult

_logger = get_logger("benchmark")


class BenchmarkRunner:
    """多模型代码修复能力评测引擎，生成排行榜"""

    def __init__(self, judge: Judge) -> None:
        self._judge = judge

    def run(self, targets: list[TargetSpec], models: list[LLMClient]) -> list[BenchmarkResult]:
        """对每个靶机目标使用各模型进行修复并评分"""
        _logger.info("Benchmark 开始: targets=%d, models=%d", len(targets), len(models))

        results: list[BenchmarkResult] = []
        for target in targets:
            _logger.info("开始评测靶机: %s", target.name)
            scores: list[ModelScore] = []
            for model in models:
                agent = BlueTeamAgent(model)
                start = time.perf_counter()
                fixed_code = agent.generate_fix(target)
                elapsed = time.perf_counter() - start

                report = self._judge.judge_normal(target, fixed_code)
                pass_rate = report.passed / report.total_tests if report.total_tests > 0 else 0.0

                original_lines = len(target.code.strip().splitlines())
                fixed_lines = len(fixed_code.strip().splitlines())
                bloat_ratio = fixed_lines / original_lines if original_lines > 0 else 1.0

                _logger.info(
                    "模型评测: model=%s, elapsed=%.2fs, pass_rate=%.4f, bloat_ratio=%.4f",
                    model._model or model._backend, elapsed, pass_rate, bloat_ratio,
                )

                detail_dicts = [
                    {
                        "test_name": d.test_name,
                        "passed": d.passed,
                        "error": d.error,
                    }
                    for d in report.details
                ]

                score = ModelScore(
                    model_name=model._model or model._backend,
                    fix_pass_rate=round(pass_rate, 4),
                    code_bloat_ratio=round(bloat_ratio, 4),
                    avg_time_seconds=round(elapsed, 4),
                    details=detail_dicts,
                )
                scores.append(score)
            results.append(BenchmarkResult(target_name=target.name, scores=scores))

        _logger.info(
            "Benchmark 结束: 共 %d 个靶机, %d 个模型, %d 条结果",
            len(targets), len(models), len(results),
        )
        return results

    def leaderboard(self, results: list[BenchmarkResult]) -> str:
        """生成可读的排行榜文本"""
        lines: list[str] = []
        for br in results:
            lines.append(f"靶机: {br.target_name}")
            lines.append("-" * 50)
            sorted_scores = sorted(br.scores, key=lambda s: s.fix_pass_rate, reverse=True)
            for rank, score in enumerate(sorted_scores, 1):
                lines.append(
                    f"  #{rank} {score.model_name} | "
                    f"通过率: {score.fix_pass_rate:.2%} | "
                    f"膨胀率: {score.code_bloat_ratio:.2f}x | "
                    f"耗时: {score.avg_time_seconds:.2f}s"
                )
            lines.append("")
        return "\n".join(lines)
