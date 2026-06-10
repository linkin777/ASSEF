"""ASSEF 数据模型层 —— 所有纯数据定义（Pydantic模型、dataclass）"""
from .target_spec import TargetSpec, SuccessCriteria, NormalTest
from .results import SandboxResult, VerdictDetail, VerdictReport
from .benchmark_result import ModelScore, BenchmarkResult
from .arena_result import RoundRecord, ArenaResult, ArenaReport
from .game_rules import GameRules
from .constitution import Constitution
from .recorder import CallerType, Metrics, RecordEntry
from .config import (
    Config,
    LLMBackendConfig,
    GameRulesConfig,
    SandboxConfig,
    ConstitutionConfig,
    TargetConfig,
    SuccessCriteriaConfig,
    NormalTestConfig,
    load_config,
    build_target_spec_from_config,
)
