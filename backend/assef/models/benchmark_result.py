"""ASSEF 评测结果数据模型 —— 模型得分与基准测试结果"""

from dataclasses import dataclass, field


@dataclass
class ModelScore:
    """单个模型的评测得分

    Attributes:
        model_name: 模型名称
        fix_pass_rate: 修复通过率（0.0 ~ 1.0）
        code_bloat_ratio: 代码膨胀率（修复代码长度 / 原始代码长度）
        avg_time_seconds: 平均执行耗时（秒）
        details: 各靶机的详细评测记录
    """
    model_name: str
    fix_pass_rate: float
    code_bloat_ratio: float
    avg_time_seconds: float
    details: list[dict] = field(default_factory=list)


@dataclass
class BenchmarkResult:
    """单轮基准测试的汇总结果

    Attributes:
        target_name: 靶机名称
        scores: 各模型的得分列表
    """
    target_name: str
    scores: list[ModelScore] = field(default_factory=list)
