"""ASSEF 裁判结果数据模型 —— 沙箱执行结果与判定报告的数据结构"""

from dataclasses import dataclass, field


@dataclass
class SandboxResult:
    """沙箱执行结果

    Attributes:
        stdout: 子进程标准输出
        stderr: 子进程标准错误输出（含 Python traceback）
        exit_code: 进程退出码（0=正常，-1=异常/被拦截）
        timed_out: 是否因超时被终止
        elapsed_seconds: 执行耗时（秒，使用 perf_counter 高精度计时）
        sandbox_output: 可读的执行摘要（执行内容、输入格式、输出格式）
    """
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    elapsed_seconds: float
    sandbox_output: str = ""


@dataclass
class VerdictDetail:
    """单条测试的判定详情

    Attributes:
        test_name: 测试名称
        input: 输入数据（攻击载荷或正常输入）
        expected_output: 期望输出（攻击测试为None）
        actual_output: 实际输出
        passed: 是否通过
        error: 失败原因（通过时为None）
    """
    test_name: str
    input: dict
    expected_output: str | None
    actual_output: str
    passed: bool
    error: str | None


@dataclass
class VerdictReport:
    """判定汇总报告

    Attributes:
        total_tests: 总测试数
        passed: 通过数
        failed: 失败数
        attack_success: 是否存在成功的攻击
        defense_passed: 蓝队防御是否通过（所有正常测试通过且攻击被拦截）
        cost_score: 蓝队防御代价评分 0.0-1.0
        details: 每条测试的判定详情
    """
    total_tests: int
    passed: int
    failed: int
    attack_success: bool
    defense_passed: bool = False
    cost_score: float = 0.0
    details: list = field(default_factory=list)
