"""ASSEF 宪法数据模型 —— 裁判系统的根本规则与判定标准"""

from dataclasses import dataclass


@dataclass
class Constitution:
    """ASSEF 裁判系统宪法 —— 定义攻击/修复/评分的根本规则

    Attributes:
        preamble: 前言（宪法宗旨说明）
        attack_success_criteria: 攻击成功判定标准
        fix_success_criteria: 修复成功判定标准
        scoring_rules: 红蓝评分规则
        constraints: 判官脚本技术约束
    """
    preamble: str
    attack_success_criteria: str
    fix_success_criteria: str
    scoring_rules: str
    constraints: str

    @classmethod
    def default(cls) -> "Constitution":
        """返回默认宪法实例 —— 包含预设的攻击/修复/评分规则"""
        return cls(
            preamble=(
                "本宪法为ASSEF红蓝对抗裁判系统的基础规则。"
                "所有判官脚本必须依据本宪法生成，"
                "确保判定的一致性和可解释性。"
            ),
            attack_success_criteria=(
                "攻击成功判定：红队的攻击输入导致靶机返回了不应暴露的数据。"
                "具体而言：(1)输出中包含了仅管理员可访问的敏感信息(如flag、secret、admin数据)；"
                "(2)输出泄露了系统内部状态或所有用户数据；"
                "(3)攻击输入绕过了正常的输入校验逻辑。"
                "若以上任一条件满足，则判定攻击成功。"
            ),
            fix_success_criteria=(
                "修复成功判定：蓝队的修复代码必须同时满足："
                "(1)所有正常功能测试用例全部通过；"
                "(2)所有已知攻击输入均被拦截（不再泄露敏感数据）；"
                "(3)代码变更最小化，不引入不必要的复杂逻辑。"
            ),
            scoring_rules=(
                "红蓝加减分权重："
                "红队：每次成功攻击+10分。"
                "蓝队：防御性价比指数 = 拦截率×0.5 - 性能退化系数×0.2 - 代码膨胀系数×0.15 - 可读性惩罚×0.15。"
                "蓝队提交最终代码通过防御评估则+15*cost_score分。"
                "蓝队提交最终代码无法通过正常功能测试则-10分（功能严重退化重罚）。"
                "蓝队拒绝提交代码则-5分。"
            ),
            constraints=(
                "判官脚本技术约束："
                "1. 必须为纯Python函数 def judge(inputs: list[dict], original_code_len: int, new_code_len: int) -> dict。"
                "2. 仅可使用 json, re, str, dict, list, bool, int, float 等内置模块。"
                "3. 禁止 import os, subprocess, sys, socket, requests 等外部或危险模块。"
                "4. 函数无副作用，不读写文件系统，不发起网络请求。"
                "5. 每条 input 格式: {'name': str, 'input': dict, 'expected_output': str|None, 'actual_output': str, 'stderr': str, 'exit_code': int, 'timed_out': bool, 'elapsed_time': float}。"
                "6. 返回格式: {'attack_success': bool, 'defense_passed': bool, 'results': [{'name': str, 'passed': bool, 'reason': str}], 'cost_score': float}。"
                "7. cost_score 计算需考虑原始代码行数(original_code_len)和新代码行数(new_code_len)的膨胀比例。"
            ),
        )
