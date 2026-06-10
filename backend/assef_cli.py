"""ASSEF CLI —— 命令行红蓝对抗工具

用法:
    python backend/assef_cli.py run [--target NAME] [--rounds N]
    python backend/assef_cli.py info

终端输出精简，详细信息记录在 backend/logs/ 日志文件中。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.assef.agents import RedTeamAgent, BlueTeamAgent
from backend.assef.arena import Arena
from backend.assef.cli_display import DisplayState, CliRenderer
from backend.assef.history import save_arena_result, list_records, get_detail, delete_record
from backend.assef.judge import ConstitutionJudge
from backend.assef.llm import LLMClient
from backend.assef.logging_config import setup_logging, get_logger
from backend.assef.models import Constitution, GameRules
from backend.assef.models.config import load_config, build_target_spec_from_config

_logger = get_logger("cli")

STATUS_ICONS = {
    "running": "⏳",
    "done": "✅",
    "failed": "❌",
    "attack": "🔴",
    "defense": "🟢",
}


def _quiet_console() -> None:
    console_handler = None
    root = logging.getLogger("assef")
    for h in root.handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            h.setLevel(logging.ERROR)
            console_handler = h
            break


def cmd_history_list(record_type: str | None, limit: int) -> None:
    records = list_records(record_type=record_type, page=1, page_size=limit)
    items = records.get("items", [])
    total = records.get("total", 0)

    if not items:
        print(f"暂无历史记录。")
        return

    print("═" * 80)
    print(f"历史记录 ({total} 条)")
    print("═" * 80)

    for i, item in enumerate(items):
        record_id = item.get("record_id", "")
        rtype = item.get("record_type", "")
        created = item.get("created_at", "")
        type_label = "竞技场" if rtype == "arena" else "排行榜" if rtype == "benchmark" else rtype

        if rtype == "arena":
            print(f"\n[{i + 1}] {type_label} | {created}")
            print(f"    ID: {record_id}")
            print(f"    靶机: {item.get('target_name', '')}")
            print(f"    回合: {item.get('total_rounds', 0)} | 红队: {item.get('red_score', 0):.1f} | 蓝队: {item.get('blue_score', 0):.1f}")
        elif rtype == "benchmark":
            print(f"\n[{i + 1}] {type_label} | {created}")
            print(f"    ID: {record_id}")
            print(f"    靶机: {', '.join(item.get('target_names', []))}")
            print(f"    模型: {', '.join(item.get('model_names', []))}")


def cmd_history_show(record_id: str) -> None:
    data = get_detail(record_id)
    if data is None:
        print(f"错误: 记录 {record_id} 不存在", file=sys.stderr)
        sys.exit(1)

    import json

    print("═" * 80)
    print(f"记录详情: {record_id}")
    print("═" * 80)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_info(config_path: str) -> None:
    config = load_config(config_path)

    print("═" * 50)
    print("ASSEF 配置信息")
    print("═" * 50)

    print(f"\nLLM 后端 ({len(config.llm_backends)} 个):")
    for be in config.llm_backends:
        print(f"  - {be.backend}/{be.model}")

    print(f"\n靶机 ({len(config.targets)} 个):")
    for t in config.targets:
        print(f"  - {t.name}: {t.description[:60]}...")

    rules = config.game_rules
    print(f"\n游戏规则:")
    print(f"  - 默认回合数: {rules.max_arena_rounds}")
    print(f"  - 蓝队最大重试: {rules.max_blue_retries}")
    print(f"  - 红队早期计划数: {rules.red_max_plans_early}")
    print(f"  - 红队后期计划数: {rules.red_max_plans_late}")

    print(f"\n宪法摘要: {config.constitution.preamble[:80]}...")
    print(f"\n配置路径: {Path(config_path).resolve()}")


def cmd_run(config_path: str, target_name: str | None, rounds: int) -> None:
    setup_logging()
    _quiet_console()

    config = load_config(config_path)
    if not config.llm_backends:
        print("错误: config.json 中没有配置 LLM 后端", file=sys.stderr)
        sys.exit(1)
    if not config.targets:
        print("错误: config.json 中没有配置靶机", file=sys.stderr)
        sys.exit(1)

    if target_name:
        target_config = next((t for t in config.targets if t.name == target_name), None)
        if target_config is None:
            print(f"错误: 未找到靶机 '{target_name}'", file=sys.stderr)
            print(f"可用靶机: {', '.join(t.name for t in config.targets)}", file=sys.stderr)
            sys.exit(1)
    else:
        target_config = config.targets[0]

    backend_conf = config.llm_backends[0]
    target = build_target_spec_from_config(target_config)

    red_llm = LLMClient.from_config(backend_conf)
    blue_llm = LLMClient.from_config(backend_conf)
    judge_llm = LLMClient.from_config(backend_conf)

    constitution = Constitution(
        preamble=config.constitution.preamble,
        attack_success_criteria=config.constitution.attack_success_criteria,
        fix_success_criteria=config.constitution.fix_success_criteria,
        scoring_rules=config.constitution.scoring_rules,
        constraints=config.constitution.constraints,
    )

    rules = GameRules(
        max_blue_retries=config.game_rules.max_blue_retries,
        performance_degrade_limit=config.game_rules.performance_degrade_limit,
        code_bloat_limit=config.game_rules.code_bloat_limit,
        red_strategy_mutation_threshold=config.game_rules.red_strategy_mutation_threshold,
        max_arena_rounds=rounds,
        self_adversary_attempts=config.game_rules.self_adversary_attempts,
        blue_self_iteration_limit=config.game_rules.blue_self_iteration_limit,
        red_max_plans_early=config.game_rules.red_max_plans_early,
        red_max_plans_late=config.game_rules.red_max_plans_late,
    )

    red_team = RedTeamAgent(red_llm, rules=rules)
    blue_team = BlueTeamAgent(blue_llm)
    sandbox_desc = config.sandbox.description if config.sandbox and config.sandbox.description else ""
    constitution_judge = ConstitutionJudge(constitution, target, judge_llm, sandbox_description=sandbox_desc)

    arena = Arena(
        judge=constitution_judge,
        red_team=red_team,
        blue_team=blue_team,
        rules=rules,
    )

    # ── 全屏显示模式 ─────────────────────────────────────────────────────
    state = DisplayState(
        target_name=target.name,
        target_desc=target.description[:60],
        current_round=0,
        total_rounds=rounds,
    )
    renderer = CliRenderer()

    # 初始渲染：显示等待对抗开始的界面
    state.judge_phase = "idle"
    renderer.render(state)

    def on_llm_progress(phase: str, token: str, cumulative_chars: int):
        if phase == "output":
            state.llm_progress = f"生成中... {cumulative_chars}字符"
            renderer.render(state)

    def on_progress(event):
        step = getattr(event, "step_name", "")
        role = getattr(event, "role", "")
        etype = getattr(event, "type", "")
        data = getattr(event, "data", {}) or {}
        content = getattr(event, "content", "")

        # ── 判官：生成判词脚本 ──
        if role == "judge" and step == "setup_judge":
            if etype == "step_start":
                state.judge_phase = "generating_script"
                state.llm_progress = "生成判词脚本中..."
            elif etype == "step_done":
                state.judge_phase = "idle"
                state.llm_progress = ""

        # ── 判官：判词就绪事件 ──
        if etype == "info" and role == "judge" and step == "judge_script_ready":
            pass  # 仅记录，不改变 UI 状态

        # ── 竞技场：回合开始 ──
        if step == "round":
            if etype == "step_start":
                rn = data.get("round_num", state.current_round + 1)
                state.current_round = rn
                # 重置当前轮次数据
                state.attack_success = None
                state.defense_passed = None
                state.cost_score = 0.0
                state.sandbox_stdout = ""
                state.sandbox_stderr = ""
                state.sandbox_exit_code = 0
                state.sandbox_elapsed = 0.0
                state.sandbox_timed_out = False
                state.attack_script_preview = ""
                state.judge_details = []
                state.blue_iterations = 0

        # ── 红队：生成攻击脚本 ──
        if role == "red_team" and step == "generate_attack":
            if etype == "step_start":
                state.red_phase = "generating_attack"
                state.llm_progress = "红队生成攻击脚本..."
            elif etype == "step_done":
                state.red_phase = "sandbox_exec"
                state.llm_progress = ""
                # 从 event 中提取攻击脚本信息
                if content:
                    state.attack_script_preview = content[:1000]

        # ── 沙盒执行 ──
        if etype == "info" and role == "arena" and step == "sandbox_exec":
            state.red_phase = "sandbox_exec"
            state.judge_phase = "judging_attack"
            state.sandbox_exit_code = data.get("exit_code", 0)
            state.sandbox_elapsed = data.get("elapsed_time", 0)
            state.sandbox_timed_out = data.get("timed_out", False)
            state.sandbox_stdout = data.get("stdout", "")
            state.sandbox_stderr = data.get("stderr", "")

        # ── 判官：攻击判定结果（通过 score_update 事件推断） ──
        if etype == "info" and role == "judge":
            if step == "sandbox_done":
                # 攻防测试完成
                pass
            elif step == "sandbox_exec":
                state.judge_phase = "judging_attack"

        # ── 蓝队：修复/增强 ──
        if step == "try_defense":
            if etype == "step_start":
                mode = data.get("mode", "fix")
                state.blue_phase = "fixing" if mode == "fix" else "enhancing"
                state.llm_progress = "蓝队生成修复代码..."
                state.judge_details = []
            elif etype == "step_done":
                state.blue_phase = "verifying"
                state.judge_phase = "judging_defense"
                state.defense_passed = data.get("defense_passed", False)
                state.llm_progress = ""

        # ── 得分更新（关键事件） ──
        if etype == "score_update":
            state.red_score = data.get("red_score", state.red_score)
            state.blue_score = data.get("blue_score", state.blue_score)
            atk_success = data.get("attack_success", False)
            def_passed = data.get("defense_passed", False)
            cs = data.get("cost_score", 0.0)
            state.attack_success = atk_success
            state.defense_passed = def_passed
            state.cost_score = cs
            state.round_summaries.append({
                "round_num": data.get("round_num", state.current_round),
                "total_rounds": rounds,
                "attack_success": atk_success,
                "defense_passed": def_passed,
                "cost_score": cs,
            })
            state.judge_phase = "idle"
            state.blue_phase = "idle"

        # ── 判官测试详情 ──
        if etype == "judge_test_result":
            state.judge_details.append({
                "name": data.get("test_name", "?"),
                "passed": data.get("passed", False),
                "reason": data.get("reason", ""),
            })

        renderer.render(state)

    # ── 运行竞技场 ──
    result = arena.run(target, rounds, on_progress=on_progress, on_llm_progress=on_llm_progress)
    save_arena_result(result)

    # ── 提取最终修复代码供展示 ──
    _fix_code: str | None = None
    for r in reversed(result.rounds):
        if r.defense_passed and r.defense_code:
            _fix_code = r.defense_code
            break
    if not _fix_code:
        for r in reversed(result.rounds):
            if r.defense_code:
                _fix_code = r.defense_code
                break
    if _fix_code:
        state.fix_code = _fix_code
        # save_arena_result 已保存 fix code 文件，查找最新匹配文件路径
        fixes_dir = Path(__file__).resolve().parent.parent / "history" / "fixes"
        safe_target = "".join(c if c.isalnum() or c in "_-" else "_" for c in result.target_name)
        candidates = sorted(fixes_dir.glob(f"{safe_target}_*.py"), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            state.fix_code_path = str(candidates[0])

    # ── 对抗结束：填充最终状态并显示判官报告 ──
    state.arena_finished = True
    state.red_phase = "idle"
    state.blue_phase = "idle"
    state.judge_phase = "idle"
    state.llm_progress = ""
    state.current_round = result.total_rounds

    # 读取判官 AI 报告
    if result.report_path:
        state.report_path = result.report_path
        try:
            report_path = Path(result.report_path)
            if report_path.exists():
                import json as _json
                report_data = _json.loads(report_path.read_text(encoding="utf-8"))
                state.report_text = report_data.get("report_text", "")
        except Exception:
            state.report_text = "（报告读取失败）"

    # 最终渲染
    renderer.render(state)

    # 恢复光标
    sys.stdout.write("\033[?25h\n")
    sys.stdout.flush()


def cmd_run_all(
    config_path: str,
    targets: list[str] | None = None,
    rounds: int = 5,
) -> None:
    """对全部（或指定）靶机依次运行竞技场对抗

    Args:
        config_path: 配置文件路径
        targets: 靶机名称列表，默认 None 表示全部
        rounds: 每个靶机的对抗回合数
    """
    setup_logging()
    config = load_config(config_path)
    if not config.llm_backends:
        print("错误: config.json 中没有配置 LLM 后端", file=sys.stderr)
        sys.exit(1)
    if not config.targets:
        print("错误: config.json 中没有配置靶机", file=sys.stderr)
        sys.exit(1)

    backend_conf = config.llm_backends[0]

    if targets:
        target_configs = [t for t in config.targets if t.name in targets]
        if not target_configs:
            print(f"错误: 未找到匹配的靶机 {targets}", file=sys.stderr)
            print(f"可用靶机: {', '.join(t.name for t in config.targets)}", file=sys.stderr)
            sys.exit(1)
    else:
        target_configs = list(config.targets)

    print(f"批量对抗: {len(target_configs)} 个靶机，每靶机 {rounds} 回合")
    print(f"模型: {backend_conf.model}")
    print("═" * 60)

    summary_rows: list[dict] = []
    total_attack_success = 0
    total_defense_passed = 0

    for i, target_config in enumerate(target_configs):
        target_name = target_config.name
        print(f"\n[{i + 1}/{len(target_configs)}] 正在对抗: {target_name} ...")

        try:
            target = build_target_spec_from_config(target_config)

            red_llm = LLMClient.from_config(backend_conf)
            blue_llm = LLMClient.from_config(backend_conf)
            judge_llm = LLMClient.from_config(backend_conf)

            constitution = Constitution(
                preamble=config.constitution.preamble,
                attack_success_criteria=config.constitution.attack_success_criteria,
                fix_success_criteria=config.constitution.fix_success_criteria,
                scoring_rules=config.constitution.scoring_rules,
                constraints=config.constitution.constraints,
            )

            rules = GameRules(
                max_blue_retries=config.game_rules.max_blue_retries,
                performance_degrade_limit=config.game_rules.performance_degrade_limit,
                code_bloat_limit=config.game_rules.code_bloat_limit,
                red_strategy_mutation_threshold=config.game_rules.red_strategy_mutation_threshold,
                max_arena_rounds=rounds,
                self_adversary_attempts=config.game_rules.self_adversary_attempts,
                blue_self_iteration_limit=config.game_rules.blue_self_iteration_limit,
                red_max_plans_early=config.game_rules.red_max_plans_early,
                red_max_plans_late=config.game_rules.red_max_plans_late,
            )

            red_team = RedTeamAgent(red_llm, rules=rules)
            blue_team = BlueTeamAgent(blue_llm)
            sandbox_desc = config.sandbox.description if config.sandbox and config.sandbox.description else ""
            constitution_judge = ConstitutionJudge(constitution, target, judge_llm, sandbox_description=sandbox_desc)

            arena = Arena(
                judge=constitution_judge,
                red_team=red_team,
                blue_team=blue_team,
                rules=rules,
            )

            result = arena.run(target, rounds)
            save_arena_result(result)

            attack_success_count = sum(1 for r in result.rounds if r.attack_success)
            defense_passed_count = sum(1 for r in result.rounds if r.defense_passed)
            total_attack_success += attack_success_count
            total_defense_passed += defense_passed_count

            # 查找已保存的修复代码路径
            safe_target_fc = "".join(c if c.isalnum() or c in "_-" else "_" for c in target_name)
            fixes_glob = list((Path(__file__).resolve().parent.parent / "history" / "fixes").glob(f"{safe_target_fc}_*.py"))
            _fc_display = ""
            if fixes_glob:
                latest_fc = sorted(fixes_glob, key=lambda p: p.stat().st_mtime, reverse=True)[0]
                _fc_display = f"\n     💾 修复代码 → {latest_fc}"

            summary_rows.append({
                "target_name": target_name,
                "total_rounds": result.total_rounds,
                "red_score": result.red_score,
                "blue_score": result.blue_score,
                "attack_success_count": attack_success_count,
                "defense_passed_count": defense_passed_count,
                "error": None,
            })

            print(f"  ✅ {target_name}: 红队 {result.red_score:.1f} : 蓝队 {result.blue_score:.1f} "
                  f"(攻击成功 {attack_success_count}/{result.total_rounds}, 防御通过 {defense_passed_count}/{result.total_rounds}){_fc_display}")

        except Exception as e:
            _logger.error("靶机 %s 对抗失败: %s", target_name, e, exc_info=True)
            summary_rows.append({
                "target_name": target_name,
                "total_rounds": 0,
                "red_score": 0,
                "blue_score": 0,
                "attack_success_count": 0,
                "defense_passed_count": 0,
                "error": str(e),
            })
            print(f"  ❌ {target_name}: 失败 — {e}")

    # 汇总表格
    print("\n" + "═" * 80)
    print("批量对抗汇总")
    print("═" * 80)
    header = f"  {'靶机':<25} {'回合':<6} {'红分':<8} {'蓝分':<8} {'攻击成功':<8} {'防御成功':<8}"
    print(header)
    print("  " + "─" * (len(header) - 2))

    for row in summary_rows:
        if row["error"]:
            status = f"❌ {row['error'][:30]}"
            print(f"  {row['target_name']:<25} {'—':<6} {'—':<8} {'—':<8} {'—':<8} {'—':<8}  {status}")
        else:
            print(f"  {row['target_name']:<25} {row['total_rounds']:<6} "
                  f"{row['red_score']:<8.1f} {row['blue_score']:<8.1f} "
                  f"{row['attack_success_count']:<8} {row['defense_passed_count']:<8}")

    total_targets = len(summary_rows)
    success_targets = sum(1 for r in summary_rows if r["error"] is None)
    print("  " + "─" * (len(header) - 2))
    print(f"  共 {total_targets} 个靶机，成功 {success_targets} 个，失败 {total_targets - success_targets} 个")
    print(f"  总攻击成功次数: {total_attack_success}，总防御成功次数: {total_defense_passed}")
    print(f"详细日志: {Path(__file__).resolve().parent / 'logs'}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ASSEF 命令行红蓝对抗工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
                示例:
                python backend/assef_cli.py info                    查看配置信息
                python backend/assef_cli.py run                     默认 4 回合对抗
                python backend/assef_cli.py run --target user-query --rounds 5
                python backend/assef_cli.py run-all                 全部靶机批量对抗
                python backend/assef_cli.py run-all --rounds 3      指定回合数批量对抗
                python backend/assef_cli.py run-all --targets target1 target2
        """,
    )
    parser.add_argument("--config", default="config.json", help="配置文件路径 (默认: config.json)")

    sub = parser.add_subparsers(dest="command", help="子命令")

    sub.add_parser("info", help="显示配置信息（靶机、LLM 后端、规则）")

    run_parser = sub.add_parser("run", help="启动红蓝对抗")
    run_parser.add_argument("--target", type=str, default=None, help="靶机名称 (默认: config 中第一个)")
    run_parser.add_argument("--rounds", type=int, default=4, help="对抗回合数 (默认: 4)")

    run_all_parser = sub.add_parser("run-all", help="批量运行全部靶机对抗")
    run_all_parser.add_argument("--rounds", type=int, default=5, help="每个靶机的对抗回合数 (默认: 5)")
    run_all_parser.add_argument("--targets", type=str, nargs="*", default=None, help="靶机名称列表，默认全部")

    history_parser = sub.add_parser("history", help="查询历史记录")
    hist_sub = history_parser.add_subparsers(dest="hist_cmd", help="子命令")

    hist_list = hist_sub.add_parser("list", help="列出历史记录")
    hist_list.add_argument("--type", type=str, choices=["arena", "benchmark"], default=None, help="筛选类型")
    hist_list.add_argument("--limit", type=int, default=20, help="显示条数 (默认: 20)")

    hist_show = hist_sub.add_parser("show", help="查看历史记录详情")
    hist_show.add_argument("record_id", type=str, help="记录 ID")

    args = parser.parse_args()

    if args.command == "info":
        cmd_info(args.config)
    elif args.command == "run":
        cmd_run(args.config, args.target, args.rounds)
    elif args.command == "run-all":
        cmd_run_all(args.config, args.targets, args.rounds)
    elif args.command == "history":
        if args.hist_cmd == "list":
            cmd_history_list(args.type, args.limit)
        elif args.hist_cmd == "show":
            cmd_history_show(args.record_id)
        else:
            history_parser.print_help()
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
