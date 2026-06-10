"""ASSEF 竞技场结果数据模型 —— 回合记录与竞技场结果"""

from dataclasses import dataclass, field


@dataclass
class RoundRecord:
    """单轮对抗记录

    Attributes:
        round_num: 回合编号
        attack_script: 红队生成的攻击脚本源代码
        successful_attacks: 本轮所有成功的攻击载荷
        attack_success: 任一攻击是否成功
        attack_output: 首个成功攻击的输出摘要（最多500字符）
        defense_code: 蓝队防御代码（可为None）
        defense_passed: 防御是否通过
        eval_red: 评估是否为红（攻击成功）
        eval_yellow: 评估是否为黄（部分成功）
        eval_green: 评估是否为绿（防御成功）
        cost_score: 成本得分
        blue_retries: 蓝队重试次数
    """
    round_num: int
    attack_script: str = ""
    successful_attacks: list[dict] = field(default_factory=list)
    attack_success: bool = False
    attack_output: str = ""
    defense_code: str | None = None
    defense_passed: bool = False
    eval_red: bool = False
    eval_yellow: bool = False
    eval_green: bool = False
    cost_score: float = 0.0
    blue_retries: int = 0


@dataclass
class ArenaReport:
    """AI 生成的竞技场分析报告

    Attributes:
        target_name: 靶机名称
        generated_at: 生成时间（ISO 格式）
        total_rounds: 总回合数
        red_score: 红队总得分
        blue_score: 蓝队总得分
        report_text: AI 生成的完整报告文本
        sections: 解析后的报告章节（如有）
    """
    target_name: str
    generated_at: str
    total_rounds: int
    red_score: float
    blue_score: float
    report_text: str
    sections: dict = field(default_factory=dict)


@dataclass
class ArenaResult:
    """竞技场最终结果

    Attributes:
        target_name: 靶机名称
        total_rounds: 总回合数
        red_score: 红队总得分
        blue_score: 蓝队总得分
        rounds: 每轮对抗记录
        events: 事件时间线
        report_path: 生成的 AI 报告文件路径
    """
    target_name: str
    total_rounds: int
    red_score: float
    blue_score: float
    rounds: list[RoundRecord] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    report_path: str = ""
