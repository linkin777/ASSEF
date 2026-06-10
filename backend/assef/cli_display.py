"""ASSEF CLI 专业终端展示系统

采用分区域 ANSI 布局，原地覆盖渲染防止 UI 重复：
- 顶部标题栏：靶机信息 + 回合进度条 + 实时比分
- 右侧恒定状态区：红队/蓝队/判官 三方实时状态
- 中间主区域：沙盒执行详情 / 判官评分过程 / 当前轮次关键事件
- 底部：历史回合摘要 + 轮次结束分隔线
- 对抗结束后：判官 AI 总结报告全文展示
"""

from __future__ import annotations

import sys
import shutil
import textwrap
from dataclasses import dataclass, field

# ── ANSI 颜色常量 ──────────────────────────────────────────────────────────
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
WHITE = "\033[97m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

CURSOR_HIDE = "\033[?25l"
CURSOR_SHOW = "\033[?25h"
CURSOR_HOME = "\033[H"
CLEAR_BELOW = "\033[J"
CLEAR_SCREEN = "\033[2J\033[H"

# ── DisplayState ────────────────────────────────────────────────────────────


@dataclass
class DisplayState:
    """CLI 展示状态数据模型"""
    target_name: str = ""
    target_desc: str = ""
    current_round: int = 0
    total_rounds: int = 0
    red_score: float = 0.0
    blue_score: float = 0.0
    red_phase: str = "idle"
    blue_phase: str = "idle"
    judge_phase: str = "idle"
    llm_progress: str = ""
    attack_script_preview: str = ""
    sandbox_stdout: str = ""
    sandbox_stderr: str = ""
    sandbox_exit_code: int = 0
    sandbox_elapsed: float = 0.0
    sandbox_timed_out: bool = False
    judge_details: list[dict] = field(default_factory=list)
    attack_success: bool | None = None
    defense_passed: bool | None = None
    cost_score: float = 0.0
    blue_iterations: int = 0
    round_summaries: list[dict] = field(default_factory=list)
    report_text: str = ""
    report_path: str = ""
    arena_finished: bool = False
    fix_code: str = ""
    fix_code_path: str = ""


# ── 辅助函数 ────────────────────────────────────────────────────────────────

def _phase_label(phase: str) -> str:
    _map = {
        "idle": "空闲",
        "generating_attack": "生成攻击脚本",
        "sandbox_exec": "沙盒执行中",
        "waiting_judge": "等待判定",
        "fixing": "修复代码中",
        "enhancing": "主动加固中",
        "verifying": "自检验收中",
        "generating_script": "生成判词脚本",
        "judging_attack": "判定攻击结果",
        "judging_defense": "判定防御效果",
    }
    return _map.get(phase, phase)


def _result_badge(success: bool | None) -> str:
    if success is True:
        return f"{GREEN}✓ 成功{RESET}"
    elif success is False:
        return f"{RED}✗ 失败{RESET}"
    return f"{DIM}⏳ 等待中{RESET}"


def _progress_bar(current: int, total: int, width: int = 20) -> str:
    if total == 0:
        return ""
    ratio = current / total
    filled = int(width * ratio)
    bar = f"{GREEN}{'█' * filled}{DIM}{'░' * (width - filled)}{RESET}"
    return f"[{bar}] {current}/{total}"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _wrap_lines(text: str, width: int) -> list[str]:
    if not text:
        return []
    return textwrap.wrap(text, width=width, replace_whitespace=False)


TERM_WIDTH = min(shutil.get_terminal_size().columns, 120)


def _visible_len(text: str) -> int:
    """去除 ANSI 转义序列后的可见字符长度"""
    import re
    return len(re.sub(r'\033\[[0-9;?]*[a-zA-Z]', '', text))


def _pad_to(text: str, width: int) -> str:
    """将字符串填充到指定可见宽度（考虑 ANSI 码）"""
    vlen = _visible_len(text)
    if vlen >= width:
        return text
    return text + ' ' * (width - vlen)


# ── CliRenderer ─────────────────────────────────────────────────────────────


class CliRenderer:
    """CLI 终端渲染器 —— 分区域 ANSI 布局，原地覆盖防止 UI 重复"""

    def __init__(self) -> None:
        self._first_render = True

    def render(self, state: DisplayState) -> None:
        # 收集输出行
        lines: list[str] = []
        lines.append(CURSOR_HIDE)
        lines.extend(self._render_header(state))
        lines.extend(self._render_body(state))
        lines.extend(self._render_footer(state))

        if state.arena_finished and state.report_text:
            lines.extend(self._render_report(state))

        # 渲染策略：首次清屏 + 全量输出，后续原地覆盖
        if self._first_render:
            sys.stdout.write(CLEAR_SCREEN + "\n".join(lines))
            self._first_render = False
        else:
            # 回到屏幕顶部，覆盖内容，清除下方残留
            sys.stdout.write(CURSOR_HOME + "\n".join(lines) + CLEAR_BELOW)

        sys.stdout.write(CURSOR_SHOW)
        sys.stdout.flush()

    # ── 标题栏 ──────────────────────────────────────────────────────────

    def _render_header(self, state: DisplayState) -> list[str]:
        w = TERM_WIDTH - 2
        target = _truncate(state.target_name, 30)
        progress = _progress_bar(state.current_round, state.total_rounds, 16)
        red_score_str = f"{RED}{state.red_score:.1f}{RESET}"
        blue_score_str = f"{BLUE}{state.blue_score:.1f}{RESET}"

        header = f" {BOLD}{WHITE}⚔ ASSEF 红蓝对抗{RESET}  │  {CYAN}{target}{RESET}  "
        header += f"{progress}  │  {RED}红{red_score_str}{RESET} : {BLUE}蓝{blue_score_str}{RESET}"

        header = _pad_to(header, w)

        return [
            f"{BOLD}{CYAN}╔{'═' * w}╗{RESET}",
            f"{BOLD}{CYAN}║{RESET}{header}{BOLD}{CYAN}║{RESET}",
            f"{BOLD}{CYAN}╚{'═' * w}╝{RESET}",
        ]

    # ── 主体：左侧状态 + 右侧主内容 ─────────────────────────────────────

    def _render_body(self, state: DisplayState) -> list[str]:
        w = TERM_WIDTH - 2
        sidebar_w = 28
        content_w = w - sidebar_w - 3

        sidebar = self._render_sidebar(state, sidebar_w)

        if state.arena_finished:
            content = self._render_final_result(state, content_w)
        else:
            content = self._render_main_content(state, content_w)

        zipped = self._zip_columns(sidebar, content, sidebar_w, content_w)
        lines: list[str] = []
        for left, right in zipped:
            lines.append(f" {left} │ {right}")
        return lines

    def _render_sidebar(self, state: DisplayState, w: int) -> list[str]:
        sep = f"{DIM}{'─' * w}{RESET}"
        lines = [
            f"{BOLD}{YELLOW}┌─ 实时状态 {'─' * (w - 11)}┐{RESET}",
        ]
        rp = _phase_label(state.red_phase)
        lines.append(f"{RED}│ ● 红队{RESET}: {_truncate(rp, w - 9)}")
        bp = _phase_label(state.blue_phase)
        lines.append(f"{BLUE}│ ● 蓝队{RESET}: {_truncate(bp, w - 9)}")
        jp = _phase_label(state.judge_phase)
        lines.append(f"{YELLOW}│ ● 判官{RESET}: {_truncate(jp, w - 9)}")

        if state.attack_success is not None or state.defense_passed is not None:
            lines.append(f"│ {sep}")
            if state.attack_success is not None:
                lines.append(f"│ 攻击: {_result_badge(state.attack_success)}")
            if state.defense_passed is not None:
                lines.append(f"│ 防御: {_result_badge(state.defense_passed)}")
            if state.cost_score > 0:
                lines.append(f"│ cost: {BOLD}{state.cost_score:.3f}{RESET}")

        if state.blue_iterations > 0:
            lines.append(f"│ 蓝队迭代: {state.blue_iterations} 次")

        if state.judge_details:
            lines.append(f"│ {sep}")
            passed = sum(1 for d in state.judge_details if d.get("passed"))
            total = len(state.judge_details)
            lines.append(f"│ 判官测试: {GREEN}{passed}{RESET}/{total} 通过")

        lines.append(f"{YELLOW}└{'─' * w}┘{RESET}")
        return lines

    def _render_main_content(self, state: DisplayState, w: int) -> list[str]:
        lines: list[str] = []

        if state.llm_progress:
            lines.append(f"{CYAN}▸ LLM 进度{RESET}: {state.llm_progress}")
            lines.append("")

        if state.red_phase in ("sandbox_exec", "waiting_judge") or state.sandbox_stdout:
            lines.append(f"{BOLD}{MAGENTA}┌── 沙盒执行详情 {'─' * (w - 16)}┐{RESET}")
            lines.append(f"{MAGENTA}│{RESET} 退出码: {state.sandbox_exit_code}  "
                         f"|  耗时: {state.sandbox_elapsed:.3f}s  "
                         f"|  超时: {'是' if state.sandbox_timed_out else '否'}")
            lines.append(f"{MAGENTA}├── stdout {'─' * (w - 12)}┤{RESET}")

            stdout_lines = _wrap_lines(state.sandbox_stdout, w - 2) if state.sandbox_stdout else ["(无输出)"]
            for sl in stdout_lines[:8]:
                lines.append(f"{MAGENTA}│{RESET} {sl}")
            if len(stdout_lines) > 8:
                lines.append(f"{MAGENTA}│{RESET} {DIM}... 共 {len(stdout_lines)} 行，已截断{RESET}")

            if state.sandbox_stderr:
                lines.append(f"{MAGENTA}├── stderr {'─' * (w - 12)}┤{RESET}")
                stderr_lines = _wrap_lines(state.sandbox_stderr, w - 2)
                for sl in stderr_lines[:4]:
                    lines.append(f"{MAGENTA}│{RESET} {RED}{sl}{RESET}")

            lines.append(f"{MAGENTA}└{'─' * w}┘{RESET}")
            lines.append("")

        if state.judge_details:
            lines.append(f"{BOLD}{YELLOW}┌── 判官评分详情 {'─' * (w - 16)}┐{RESET}")
            for detail in state.judge_details[-12:]:
                name = _truncate(detail.get("name", "?"), 30)
                passed = detail.get("passed", False)
                reason = _truncate(detail.get("reason", ""), w - 40)
                icon = f"{GREEN}✓{RESET}" if passed else f"{RED}✗{RESET}"
                lines.append(f"{YELLOW}│{RESET} {icon} {name}  {DIM}{reason}{RESET}")
            lines.append(f"{YELLOW}└{'─' * w}┘{RESET}")
            lines.append("")

        if state.attack_script_preview:
            lines.append(f"{DIM}▸ 攻击脚本预览 ({len(state.attack_script_preview)} 字符){RESET}")
            preview = _wrap_lines(state.attack_script_preview, w - 2)
            for pl in preview[:3]:
                lines.append(f"  {DIM}{_truncate(pl, w - 4)}{RESET}")
            lines.append("")

        if not lines:
            lines.append(f"{DIM}  等待对抗开始...{RESET}")

        return lines

    def _render_final_result(self, state: DisplayState, w: int) -> list[str]:
        lines: list[str] = []
        lines.append(f"{BOLD}{GREEN}┌── 对抗结果 {'─' * (w - 12)}┐{RESET}")
        lines.append(f"{GREEN}│{RESET} 靶机: {BOLD}{state.target_name}{RESET}")
        lines.append(f"{GREEN}│{RESET} 回合数: {state.total_rounds}")
        lines.append(f"{GREEN}│{RESET} 红队最终得分: {RED}{BOLD}{state.red_score:.1f}{RESET}")
        lines.append(f"{GREEN}│{RESET} 蓝队最终得分: {BLUE}{BOLD}{state.blue_score:.1f}{RESET}")

        total_attacks = sum(1 for r in state.round_summaries if r.get("attack_success"))
        total_defenses = sum(1 for r in state.round_summaries if r.get("defense_passed"))
        lines.append(f"{GREEN}│{RESET} 攻击成功: {total_attacks}/{state.total_rounds} 回合")
        lines.append(f"{GREEN}│{RESET} 防御成功: {total_defenses}/{state.total_rounds} 回合")

        if state.report_path:
            lines.append(f"{GREEN}│{RESET} 判官报告: {DIM}{state.report_path}{RESET}")
        lines.append(f"{GREEN}└{'─' * w}┘{RESET}")

        # ── 最终修复代码预览 ──
        if state.fix_code:
            code_lines = state.fix_code.splitlines()
            lines.append("")
            lines.append(f"{BOLD}{BLUE}┌── 💾 最终修复代码 {'─' * (w - 20)}┐{RESET}")
            # 展示前 20 行代码（简易语法高亮：注释=绿，字符串=黄）
            preview_lines = code_lines[:20]
            for cl in preview_lines:
                stripped = cl.strip()
                if stripped.startswith("#"):
                    lines.append(f"{BLUE}│{RESET} {GREEN}{_truncate(cl, w - 3)}{RESET}")
                elif stripped.startswith('"""') or stripped.startswith("'''"):
                    lines.append(f"{BLUE}│{RESET} {YELLOW}{_truncate(cl, w - 3)}{RESET}")
                else:
                    lines.append(f"{BLUE}│{RESET} {_truncate(cl, w - 3)}")
            if len(code_lines) > 20:
                lines.append(f"{BLUE}│{RESET} {DIM}... 共 {len(code_lines)} 行，完整代码见下方路径{RESET}")
            lines.append(f"{BLUE}└{'─' * w}┘{RESET}")
            if state.fix_code_path:
                lines.append(f"  {GREEN}💾 修复代码已保存至: {BOLD}{state.fix_code_path}{RESET}")

        return lines

    def _render_footer(self, state: DisplayState) -> list[str]:
        w = TERM_WIDTH - 2
        lines: list[str] = []

        if state.round_summaries:
            lines.append(f"\n{DIM}── 历史回合摘要 {'─' * (w - 13)}──{RESET}")
            for s in state.round_summaries[-6:]:
                rn = s.get("round_num", "?")
                atk = s.get("attack_success", False)
                dfd = s.get("defense_passed", False)
                cs = s.get("cost_score", 0.0)
                atk_icon = f"{GREEN}✓{RESET}" if atk else f"{RED}✗{RESET}"
                def_icon = f"{GREEN}✓{RESET}" if dfd else f"{RED}✗{RESET}"
                lines.append(f"  第{rn:>2}回合 攻击{atk_icon}  防御{def_icon}  cost={cs:.3f}")

        if state.attack_success is not None and state.defense_passed is not None and not state.arena_finished:
            rn = state.current_round
            atk_label = f"{GREEN}攻击成功{RESET}" if state.attack_success else f"{RED}攻击失败{RESET}"
            def_label = f"{GREEN}防御通过{RESET}" if state.defense_passed else f"{RED}防御失败{RESET}"
            sep_line = f"\n{BOLD}{CYAN}{'═' * 25} 第 {rn} 轮结束 {'═' * 25}{RESET}"
            result_line = f"  {atk_label}  │  {def_label}  │  cost={state.cost_score:.3f}"
            red_delta = "+10" if state.attack_success else "+0"
            blue_delta = f"+{15 * state.cost_score:.1f}" if state.defense_passed else ("-10" if state.attack_success and state.defense_passed is False else "+0")
            score_line = f"  {RED}红队 {red_delta}{RESET}  │  {BLUE}蓝队 {blue_delta}{RESET}  →  {RED}红{state.red_score:.1f}{RESET} : {BLUE}蓝{state.blue_score:.1f}{RESET}"
            lines.append(sep_line)
            lines.append(result_line)
            lines.append(score_line)

        return lines

    def _render_report(self, state: DisplayState) -> list[str]:
        w = TERM_WIDTH - 2
        lines: list[str] = [
            "",
            f"{BOLD}{CYAN}{'═' * w}{RESET}",
            f"{BOLD}{CYAN}  📋 判官 AI 对抗总结报告{RESET}",
            f"{BOLD}{CYAN}{'═' * w}{RESET}",
            "",
        ]

        report_lines = state.report_text.splitlines()
        for line in report_lines[:60]:
            stripped = line.strip()
            if stripped.startswith("### ") or stripped.startswith("## "):
                lines.append(f"{BOLD}{YELLOW}{stripped}{RESET}")
            elif stripped.startswith("# "):
                lines.append(f"{BOLD}{WHITE}{stripped}{RESET}")
            elif stripped.startswith("**") and stripped.endswith("**"):
                lines.append(f"{BOLD}{stripped}{RESET}")
            elif stripped.startswith("- "):
                lines.append(f"  {DIM}{stripped}{RESET}")
            elif "|" in stripped and not stripped.startswith("```"):
                lines.append(f"  {DIM}{_truncate(stripped, w - 4)}{RESET}")
            else:
                wrapped = _wrap_lines(stripped, w - 2)
                for wl in wrapped[:2]:
                    lines.append(f"  {wl}")

        if len(report_lines) > 60:
            lines.append(f"\n  {DIM}... 报告共 {len(report_lines)} 行，以上为前 60 行摘要。完整报告见: {state.report_path}{RESET}")

        lines.append(f"\n{BOLD}{CYAN}{'═' * w}{RESET}")
        return lines

    @staticmethod
    def _zip_columns(left: list[str], right: list[str], left_w: int, right_w: int) -> list[tuple[str, str]]:
        max_len = max(len(left), len(right))
        left_padded = left + [""] * (max_len - len(left))
        right_padded = right + [""] * (max_len - len(right))

        result = []
        for l, r in zip(left_padded, right_padded):
            l_fmt = _pad_to(l, left_w)[:left_w + 50]  # tolerate ANSI codes
            r_fmt = _pad_to(r, right_w)[:right_w + 50]
            result.append((l_fmt, r_fmt))
        return result
