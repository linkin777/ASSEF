import threading
import time

import pytest

from assef.judge.event_collector import EventCollector, EventType


def _make_event_data(eid: int) -> dict:
    """生成测试用的事件数据"""
    return {"attack_id": f"attack_{eid}", "score": eid * 10}


class TestEventCollectorBasic:
    """测试 EventCollector 的基本功能"""

    def test_collect_single_event(self):
        collector = EventCollector()
        collector.collect(
            event_type=EventType.ATTACK_GENERATED,
            round_num=1,
            role="red_team",
            data=_make_event_data(1),
            summary="红队第 1 轮攻击生成",
        )
        timeline = collector.get_timeline()
        assert len(timeline) == 1
        event = timeline[0]
        assert event["round_num"] == 1
        assert event["event_type"] == "ATTACK_GENERATED"
        assert event["role"] == "red_team"
        assert event["data"]["attack_id"] == "attack_1"
        assert event["summary"] == "红队第 1 轮攻击生成"
        assert "timestamp" in event

    def test_collect_multiple_events_across_rounds(self):
        collector = EventCollector()
        # 第 1 轮: 红队攻击 → 沙箱执行 → 判官评判
        collector.collect(
            EventType.ATTACK_GENERATED, 1, "red_team",
            {"attack_id": "a1"}, "生成攻击 a1",
        )
        collector.collect(
            EventType.SANDBOX_EXECUTED, 1, "judge",
            {"exec_time": 0.5}, "沙箱执行攻击 a1",
        )
        collector.collect(
            EventType.ATTACK_JUDGED, 1, "judge",
            {"passed": True}, "攻击 a1 判定通过",
        )
        # 第 1 轮: 蓝队防御
        collector.collect(
            EventType.DEFENSE_GENERATED, 1, "blue_team",
            {"defense_id": "d1"}, "蓝队生成防御 d1",
        )
        collector.collect(
            EventType.DEFENSE_EVALUATED, 1, "judge",
            {"defense_id": "d1", "passed": True}, "防御 d1 评估通过",
        )
        # 第 2 轮: 仅红队攻击
        collector.collect(
            EventType.ATTACK_GENERATED, 2, "red_team",
            {"attack_id": "a2"}, "生成攻击 a2",
        )
        collector.collect(
            EventType.SANDBOX_EXECUTED, 2, "judge",
            {"exec_time": 0.3}, "沙箱执行攻击 a2",
        )

        timeline = collector.get_timeline()
        assert len(timeline) == 7
        # 验证排序：第 1 轮事件在前
        assert all(e["round_num"] in (1, 2) for e in timeline)
        round_1_events = [e for e in timeline if e["round_num"] == 1]
        round_2_events = [e for e in timeline if e["round_num"] == 2]
        assert len(round_1_events) == 5
        assert len(round_2_events) == 2

    def test_get_timeline_sorted(self):
        """验证 get_timeline 返回按时间戳排序的事件"""
        collector = EventCollector()
        collector.collect(
            EventType.ATTACK_GENERATED, 1, "red_team",
            {}, "first",
        )
        time.sleep(0.02)
        collector.collect(
            EventType.SANDBOX_EXECUTED, 1, "judge",
            {}, "second",
        )
        time.sleep(0.02)
        collector.collect(
            EventType.ATTACK_JUDGED, 1, "judge",
            {}, "third",
        )

        timeline = collector.get_timeline()
        assert timeline[0]["summary"] == "first"
        assert timeline[1]["summary"] == "second"
        assert timeline[2]["summary"] == "third"

    def test_get_round_events_filters_correctly(self):
        collector = EventCollector()
        for r in (1, 2, 3):
            collector.collect(
                EventType.ROUND_ENDED, r, "arena",
                {"round": r}, f"第 {r} 轮结束",
            )

        round_2_events = collector.get_round_events(2)
        assert len(round_2_events) == 1
        assert round_2_events[0]["round_num"] == 2
        assert round_2_events[0]["summary"] == "第 2 轮结束"

        # 不存在的轮次返回空列表
        assert collector.get_round_events(99) == []

    def test_clear_resets_collector(self):
        collector = EventCollector()
        collector.collect(
            EventType.ATTACK_GENERATED, 1, "red_team",
            {}, "test",
        )
        assert len(collector.get_timeline()) == 1
        collector.clear()
        assert collector.get_timeline() == []

    def test_collect_with_default_summary(self):
        collector = EventCollector()
        collector.collect(
            event_type=EventType.SCORE_UPDATED,
            round_num=1,
            role="arena",
            data={"new_score": 100},
        )
        assert collector.get_timeline()[0]["summary"] == ""


class TestEventCollectorThreadSafety:
    """测试 EventCollector 的线程安全性"""

    def test_concurrent_collect(self):
        collector = EventCollector()
        thread_count = 8
        events_per_thread = 50

        def collect_events(thread_id: int):
            for i in range(events_per_thread):
                collector.collect(
                    event_type=EventType.ATTACK_GENERATED,
                    round_num=thread_id,
                    role="red_team",
                    data={"thread": thread_id, "index": i},
                    summary=f"thread_{thread_id}_event_{i}",
                )

        threads = [
            threading.Thread(target=collect_events, args=(tid,))
            for tid in range(thread_count)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        timeline = collector.get_timeline()
        assert len(timeline) == thread_count * events_per_thread

        # 验证每个线程的事件数量正确
        for tid in range(thread_count):
            round_events = collector.get_round_events(tid)
            assert len(round_events) == events_per_thread
