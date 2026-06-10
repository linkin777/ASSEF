"""ASSEF 报告生成器 —— 基于竞技场结果通过 LLM 生成分析报告"""

from __future__ import annotations

from ..llm import LLMClient
from ..logging_config import get_logger

_logger = get_logger("report_generator")


class ReportGenerator:
    """竞技场分析报告生成器

    基于竞技场对抗结果和事件时间线，通过 LLM 生成结构化的中文分析报告。
    与判官脚本生成无关，仅负责后处理阶段的分析报告。
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def generate_summary_report(
        self,
        target_name: str,
        constitution_text: str,
        arena_result_dict: dict,
        events: list[dict],
    ) -> str:
        """基于竞技场结果和事件时间线，通过 LLM 生成结构化的中文分析报告

        Args:
            target_name: 靶机名称
            constitution_text: 宪法规则文本
            arena_result_dict: 竞技场结果字典，包含各轮次的攻防记录和最终得分
            events: 收集到的所有事件列表

        Returns:
            LLM 生成的原始报告文本
        """
        # 构建事件时间线文本
        timeline_lines = []
        for e in events:
            timeline_lines.append(
                f"- [{e.get('timestamp', '?')}] 轮次{e.get('round_num', '?')} "
                f"| {e.get('event_type', '?')} | {e.get('role', '?')} | {e.get('summary', '')}"
            )

        events_text = "\n".join(timeline_lines) if timeline_lines else "（无事件记录）"

        # 构建竞技场结果文本
        import json as _json
        arena_text = _json.dumps(arena_result_dict, ensure_ascii=False, indent=2)

        system_prompt = (
            "你是一名专业的网络安全攻防对抗分析专家。你的任务是基于给定的攻防对抗数据，"
            "生成一份结构化的中文分析报告。报告必须客观、专业、有条理，基于数据而非猜测。"
        )

        user_content = f"""\
请根据以下数据生成一份详细的攻防对抗分析报告。

## 宪法规则
{constitution_text}

## 靶机信息
- 靶机名称：{target_name}

## 竞技场对战结果
```json
{arena_text}
```

## 事件时间线
{events_text}

## 报告要求

请按以下5个章节组织报告，使用 Markdown 格式：

### 1. 对抗双方策略分析
- 分析红队（攻击方）使用的攻击策略、攻击向量和技术手段
- 分析蓝队（防御方）采取的防御策略、修复措施和防护手段
- 评估双方策略的有效性和创新性

### 2. 关键攻防事件时间线
- 按时间顺序梳理攻防对抗中的关键事件
- 标注每个关键事件的轮次、角色、类型和影响
- 突出攻防态势变化的转折点

### 3. 成功率统计与趋势分析
- 统计攻击成功率和防御成功率
- 分析各轮次成功率的变化趋势
- 评估攻防双方的表现波动

### 4. 系统漏洞与防御弱点评估
- 识别系统中被成功利用的漏洞
- 评估防御措施中存在的弱点和不足
- 分析漏洞的严重程度和潜在影响

### 5. 优化建议
- 针对攻击方提出策略优化建议
- 针对防御方提出安全加固建议
- 从整体角度提出系统性改进方案

请直接输出完整的报告内容，不要包含前言或结语。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        report = self._llm.chat(messages, temperature=0.5, max_tokens=8192)
        return report
