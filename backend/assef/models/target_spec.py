"""ASSEF 靶机规格数据模型 —— 定义靶机的结构、攻击面与验收标准"""

from typing import Literal

from pydantic import BaseModel


class SuccessCriteria(BaseModel):
    """攻击成功与修复成功的判定标准关键词

    Attributes:
        attack: 攻击成功判定关键词（出现在输出中即视为攻击成功）
        fix: 修复成功判定关键词
    """
    attack: str
    fix: str


class NormalTest(BaseModel):
    """单个正常功能测试用例

    Attributes:
        name: 测试用例名称
        input: 输入数据（将作为JSON传递给靶机）
        expected_output: 期望的输出数据
    """
    name: str
    input: dict
    expected_output: dict


class TargetSpec(BaseModel):
    """靶机规格定义 —— 描述一个安全挑战的完整配置

    Attributes:
        name: 靶机名称
        description: 靶机功能描述
        sandbox_type: 沙箱类型（"process" 或 "docker"）
        sandbox_spec: 沙箱配置参数
        code: 靶机原始源代码
        public_spec: 公开的功能规格说明（供红队参考）
        attack_surface: 攻击面描述（供红队参考）
        success_criteria: 成功判定标准
        normal_tests: 正常功能测试用例列表
    """
    name: str
    description: str
    sandbox_type: Literal["process", "docker"]
    sandbox_spec: dict
    code: str
    public_spec: str
    attack_surface: str
    success_criteria: SuccessCriteria
    normal_tests: list[NormalTest]
