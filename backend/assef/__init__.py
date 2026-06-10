"""ASSEF — 对抗性系统安全自演进框架 (Adversarial System Security Evolution Framework)

本框架提供：
- 模式A（红蓝对抗）：回合制红蓝双方 AI 对抗，三维补丁评估
- 模式B（多模型评测）：多 LLM 代码修复能力排行榜

顶层导出常用类，简化外部导入：
    from assef import Arena, Judge, ProcessSandbox, LLMClient
"""

from .models import TargetSpec, SuccessCriteria, NormalTest
from .models import SandboxResult, VerdictDetail, VerdictReport
from .models import ModelScore, BenchmarkResult
from .models import RoundRecord, ArenaResult
from .models import GameRules
from .models import Constitution

from .sandbox import ProcessSandbox

from .llm import LLMClient, LLMError, LLMConnectionError, LLMErrorCode, classify_error_code

from .judge import Judge, ConstitutionAgent, ConstitutionJudge, ReportGenerator

from .agents import BlueTeamAgent, RedTeamAgent

from .arena import Arena, BenchmarkRunner
