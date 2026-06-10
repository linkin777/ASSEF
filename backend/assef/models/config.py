"""ASSEF 配置文件数据模型 —— 统一管理所有可配置项"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..logging_config import get_logger
from .target_spec import NormalTest, SuccessCriteria, TargetSpec

_logger = get_logger("config")


class GameRulesConfig(BaseModel):
    """红蓝对抗的游戏规则配置

    Attributes:
        max_blue_retries: 蓝队最大重试次数
        performance_degrade_limit: 性能退化上限倍数
        code_bloat_limit: 代码膨胀上限倍数
        red_strategy_mutation_threshold: 红队策略变异阈值
        max_arena_rounds: 竞技场最大回合数
        self_adversary_attempts: 自我对抗尝试次数
        blue_self_iteration_limit: 蓝队自我反馈回路最大迭代次数
        red_max_plans_early: 红队早期回合（1-3）最大攻击计划数
        red_max_plans_late: 红队后期回合（4+）最大攻击计划数
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


class SandboxConfig(BaseModel):
    """沙箱执行环境配置

    Attributes:
        timeout: 执行超时时间（秒）
        description: 沙箱环境描述文本（用于生成判官脚本）
        dangerous_patterns: 危险代码模式列表，用于安全检测
    """
    timeout: float = 30.0
    description: str = ""
    dangerous_patterns: list[str] = [
        "os.system",
        "subprocess",
        "__import__",
        "eval(",
        "exec(",
        "open(",
        "import socket",
        "import http",
        "import urllib",
        "import ftplib",
        "import requests",
    ]


class ConstitutionConfig(BaseModel):
    """ASSEF 裁判系统宪法规则文本配置

    Attributes:
        preamble: 前言（宪法宗旨说明）
        attack_success_criteria: 攻击成功判定标准文本
        fix_success_criteria: 修复成功判定标准文本
        scoring_rules: 红蓝评分规则文本
        constraints: 判官脚本技术约束文本
    """
    preamble: str = (
        "本宪法为ASSEF红蓝对抗裁判系统的基础规则。"
        "所有判官脚本必须依据本宪法生成，"
        "确保判定的一致性和可解释性。"
    )
    attack_success_criteria: str = (
        "攻击成功判定：红队的攻击输入导致靶机返回了不应暴露的数据。"
        "具体而言：(1)输出中包含了仅管理员可访问的敏感信息(如flag、secret、admin数据)；"
        "(2)输出泄露了系统内部状态或所有用户数据；"
        "(3)攻击输入绕过了正常的输入校验逻辑。"
        "若以上任一条件满足，则判定攻击成功。"
    )
    fix_success_criteria: str = (
        "修复成功判定：蓝队的修复代码必须同时满足："
        "(1)所有正常功能测试用例全部通过；"
        "(2)所有已知攻击输入均被拦截（不再泄露敏感数据）；"
        "(3)代码变更最小化，不引入不必要的复杂逻辑。"
    )
    scoring_rules: str = (
        "红蓝加减分权重："
        "红队：每次成功攻击+10分，连续3轮同一策略扣5分。"
        "蓝队：防御性价比指数 = 拦截率×0.5 - 性能退化系数×0.2 - 代码膨胀系数×0.15 - 可读性惩罚×0.15。"
        "防御通过评估+15分，未通过+0分（不重复重试扣分），拒绝重试-5分。"
    )
    constraints: str = (
        "判官脚本技术约束："
        "1. 必须为纯Python函数 def judge(inputs: list[dict]) -> dict。"
        "2. 仅可使用 json, re, str, dict, list, bool, int, float 等内置模块。"
        "3. 禁止 import os, subprocess, sys, socket, requests 等外部或危险模块。"
        "4. 函数无副作用，不读写文件系统，不发起网络请求。"
        "5. 每条 input 格式: {'name': str, 'input': dict, 'expected_output': str|None, 'actual_output': str}。"
        "6. 返回格式: {'attack_success': bool, 'results': [{'name': str, 'passed': bool, 'reason': str}]}。"
    )


class LLMBackendConfig(BaseModel):
    """单个 LLM 后端的完整配置

    Attributes:
        backend: 后端类型
        model: 模型名称
        api_key: API 密钥
        base_url: API 基础 URL
        max_retries: 最大重试次数
        temperature: 生成温度
        max_tokens: 最大生成 token 数
        mock_response: Mock 后端的模拟响应文本
        is_reasoning_model: 是否为 reasoning 模型（输出在 reasoning_content 字段）
    """
    backend: Literal["ollama", "openai", "deepseek", "anthropic", "mock"]
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    max_retries: int = 3
    temperature: float = 0.7
    max_tokens: int = 2048
    mock_response: str = ""
    is_reasoning_model: bool = False


class SuccessCriteriaConfig(BaseModel):
    """攻击成功与修复成功的判定标准关键词

    Attributes:
        attack: 攻击成功判定关键词
        fix: 修复成功判定关键词
    """
    attack: str
    fix: str


class NormalTestConfig(BaseModel):
    """单个正常功能测试用例

    Attributes:
        name: 测试用例名称
        input: 输入数据
        expected_output: 期望的输出数据
    """
    name: str
    input: dict
    expected_output: dict


class TargetConfig(BaseModel):
    """靶机定义配置 —— 可从 JSON 加载，支持内联代码或外部文件引用

    Attributes:
        name: 靶机名称
        description: 靶机功能描述
        sandbox_type: 沙箱类型
        sandbox_spec: 沙箱配置参数
        code_path: 外部 .py 文件路径（包含靶机源代码）
        code: 内联靶机源代码（code_path 为空时使用）
        public_spec: 公开的功能规格说明
        attack_surface: 攻击面描述
        success_criteria: 成功判定标准
        normal_tests: 正常功能测试用例列表
    """
    name: str
    description: str
    sandbox_type: Literal["process", "docker"]
    sandbox_spec: dict = {}
    code_path: str = ""
    code: str = ""
    public_spec: str
    attack_surface: str
    success_criteria: SuccessCriteriaConfig
    normal_tests: list[NormalTestConfig]


class Config(BaseModel):
    """ASSEF 顶层配置 —— 聚合所有可配置项

    Attributes:
        llm_backends: LLM 后端配置列表
        game_rules: 博弈规则配置
        constitution: 宪法规则配置
        sandbox: 沙箱配置
        targets: 靶机定义列表
    """
    llm_backends: list[LLMBackendConfig] = []
    game_rules: GameRulesConfig = GameRulesConfig()
    constitution: ConstitutionConfig = ConstitutionConfig()
    sandbox: SandboxConfig = SandboxConfig()
    targets: list[TargetConfig] = []


def load_config(filepath: str) -> Config:
    """从 JSON 文件加载配置，文件不存在或读取失败时返回默认配置

    Args:
        filepath: JSON 配置文件路径

    Returns:
        Config 实例
    """
    path = Path(filepath)
    if not path.exists():
        _logger.warning(f"{filepath} not found, using defaults")
        return Config()
    if not path.is_file():
        _logger.warning(f"{filepath} not found, using defaults")
        return Config()

    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        _logger.error(f"读取配置文件失败: {filepath}", exc_info=True)
        return Config()

    try:
        config = Config.model_validate_json(raw)
        _logger.info(
            f"配置加载成功: {filepath} "
            f"(llm_backends={len(config.llm_backends)}, targets={len(config.targets)})"
        )
        return config
    except Exception:
        _logger.error(f"配置文件校验失败: {filepath}", exc_info=True)
        return Config()


def build_target_spec_from_config(target_config: TargetConfig) -> TargetSpec:
    """将 TargetConfig 转换为 TargetSpec

    若 target_config.code_path 非空，从外部文件读取代码内容；
    否则使用 target_config.code 内联代码。

    Args:
        target_config: 靶机配置

    Returns:
        TargetSpec 实例

    Raises:
        ValueError: 代码读取失败
    """
    if target_config.code_path:
        code_path = Path(target_config.code_path)
        try:
            code = code_path.read_text(encoding="utf-8")
            _logger.debug(
                f"从外部文件加载代码: {target_config.code_path} "
                f"(行数={len(code.splitlines())})"
            )
        except Exception as e:
            _logger.error(f"读取靶机代码文件失败: {target_config.code_path}", exc_info=True)
            raise ValueError(f"读取靶机代码文件失败: {target_config.code_path} - {e}") from e
    else:
        code = target_config.code

    return TargetSpec(
        name=target_config.name,
        description=target_config.description,
        sandbox_type=target_config.sandbox_type,
        sandbox_spec=target_config.sandbox_spec,
        code=code,
        public_spec=target_config.public_spec,
        attack_surface=target_config.attack_surface,
        success_criteria=SuccessCriteria(
            attack=target_config.success_criteria.attack,
            fix=target_config.success_criteria.fix,
        ),
        normal_tests=[
            NormalTest(
                name=nt.name,
                input=nt.input,
                expected_output=nt.expected_output,
            )
            for nt in target_config.normal_tests
        ],
    )
