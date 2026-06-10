"""ASSEF 游戏规则数据模型 —— 红蓝对抗的规则配置参数"""

from dataclasses import dataclass


@dataclass
class GameRules:
    """红蓝对抗的游戏规则配置

    真实红蓝对抗流程中，红队每轮提交一个攻击脚本，蓝队提交一个修复后的代码。
    部分字段在新的简化流程中可能不再使用，但保留以维持向后兼容性。

    Attributes:
        max_blue_retries: 蓝队最大重试次数（新流程中不再使用，蓝队为一次性提交）
        performance_degrade_limit: 性能退化上限倍数
        code_bloat_limit: 代码膨胀上限倍数
        red_strategy_mutation_threshold: 红队策略变异阈值（新流程中不再使用，无策略追踪）
        max_arena_rounds: 竞技场最大回合数
        self_adversary_attempts: 自我对抗尝试次数（新流程中不再使用，无绿队评估）
        blue_self_iteration_limit: 蓝队自我反馈回路最大迭代次数（新流程中不再使用）
        red_max_plans_early: 红队早期回合（1-3）最大攻击计划数（新流程中不再使用，红队单脚本提交）
        red_max_plans_late: 红队后期回合（4+）最大攻击计划数（新流程中不再使用，红队单脚本提交）
    """
    max_blue_retries: int = 2
    performance_degrade_limit: float = 1.5
    code_bloat_limit: float = 2.0
    red_strategy_mutation_threshold: int = 3
    max_arena_rounds: int = 10
    self_adversary_attempts: int = 3
    blue_self_iteration_limit: int = 3
    red_max_plans_early: int = 3
    red_max_plans_late: int = 1
