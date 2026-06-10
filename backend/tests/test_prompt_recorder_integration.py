"""测试 PromptRecorder 提示词记录器的集成功能：回调记录、指标计算、JSONL 写入、单例模式。"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime

import pytest

from backend.assef.recorder import get_prompt_recorder, PromptRecorder
from backend.assef.llm.llm_client import LLMClient
from backend.assef.models.config import LLMBackendConfig
from backend.assef.models.recorder import RecordEntry, Metrics, CallerType


def test_from_config_with_on_call_record():
    cfg = LLMBackendConfig(backend="mock", model="test", mock_response="hello")
    calls = []
    c = LLMClient.from_config(cfg, on_call_record=lambda d: calls.append(d))
    c.set_call_context({"caller": "red_team", "round": 1})
    result = c.chat([{"role": "user", "content": "hi"}])
    assert result == "hello"
    assert len(calls) == 1
    assert calls[0]["call_context"] == {"caller": "red_team", "round": 1}
    assert calls[0]["response"] == "hello"
    assert calls[0]["backend"] == "mock"


def test_from_config_without_on_call_record():
    cfg = LLMBackendConfig(backend="mock", model="test", mock_response="hello")
    c = LLMClient.from_config(cfg)
    result = c.chat([{"role": "user", "content": "hi"}])
    assert result == "hello"


def test_stream_with_on_call_record():
    cfg = LLMBackendConfig(backend="mock", model="test", mock_response="stream-test")
    calls = []
    c = LLMClient.from_config(cfg, on_call_record=lambda d: calls.append(d))
    tokens = []
    result = c.chat_stream(
        [{"role": "user", "content": "hi"}],
        lambda t: tokens.append(t),
    )
    assert result == "stream-test"
    assert len(calls) == 1
    assert calls[0]["response"] == "stream-test"


def test_prompt_recorder_context_tracking():
    tmpdir = tempfile.mkdtemp()
    pr = PromptRecorder(tmpdir)
    e1 = RecordEntry(
        timestamp=datetime.now().isoformat(),
        caller="red_team",
        round=1,
        backend="mock",
        model="test",
        messages="msg",
        response="resp",
        duration_ms=100.0,
        metrics=Metrics(),
    )
    e2 = RecordEntry(
        timestamp=datetime.now().isoformat(),
        caller="blue_team",
        round=1,
        backend="mock",
        model="test",
        messages="msg2",
        response="resp2",
        duration_ms=200.0,
        metrics=Metrics(),
    )
    pr.record(e1)
    pr.record(e2)
    pr.update_useful_by_context(1, "red_team", True)
    pr.update_useful_by_context(1, "blue_team", False)


def test_compute_metrics_red_team():
    m = PromptRecorder.compute_metrics(
        '[{"strategy":"injection","inputs":{"q":"test"}}]',
        "red_team",
    )
    assert m.format_valid is True


def test_compute_metrics_blue_team():
    m = PromptRecorder.compute_metrics(
        "I assume you want this fixed\n```python\nx=1\n```",
        "blue_team",
    )
    assert m.format_valid is True
    assert m.intent_guessing is True


def test_compute_metrics_constitution_judge():
    m = PromptRecorder.compute_metrics(
        'def judge(inputs):\n  return {"attack_success": True}',
        "constitution_judge",
    )
    assert m.format_valid is True


def test_compute_metrics_format_rate():
    response = "Here is some explanation text.\n```python\nx = 1 + 1\n```\nHope that helps!"
    m = PromptRecorder.compute_metrics(response, "blue_team")
    assert 0.0 < m.format_rate < 1.0


def test_record_entry_to_dict():
    entry = RecordEntry(
        timestamp="2026-05-31T12:00:00",
        caller="red_team",
        round=1,
        backend="mock",
        model="test",
        messages="hi",
        response="hello",
        duration_ms=100.0,
        metrics=Metrics(),
    )
    d = entry.to_dict()
    assert d["caller"] == "red_team"
    assert d["round"] == 1
    assert "call_id" in d
    assert d["metrics"]["useful"] is None
    assert d["metrics"]["format_rate"] == 1.0
    assert d["metrics"]["intent_guessing"] is False
    json.dumps(d)


def test_record_entry_jsonl_write():
    tmpdir = tempfile.mkdtemp()
    pr = PromptRecorder(tmpdir)
    entry = RecordEntry(
        timestamp=datetime.now().isoformat(),
        caller="red_team",
        round=1,
        backend="mock",
        model="test",
        messages="test msg",
        response="test resp",
        duration_ms=100.0,
        metrics=Metrics(format_valid=True, format_rate=0.8, intent_guessing=False),
    )
    pr.record(entry)
    pr.update_useful_by_context(1, "red_team", True)

    import glob
    jsonl_files = glob.glob(f"{tmpdir}/prompt_records_*.jsonl")
    assert len(jsonl_files) == 1

    with open(jsonl_files[0], "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["caller"] == "red_team"
    assert data["metrics"]["useful"] is True
    assert data["metrics"]["format_valid"] is True


def test_call_id_uniqueness():
    e1 = RecordEntry(
        timestamp="2026-05-31T12:00:00",
        caller="red_team",
        round=1,
        backend="mock",
        model="test",
        messages="msg",
        response="resp",
        duration_ms=100.0,
        metrics=Metrics(),
    )
    e2 = RecordEntry(
        timestamp="2026-05-31T12:00:01",
        caller="blue_team",
        round=1,
        backend="mock",
        model="test",
        messages="msg",
        response="resp",
        duration_ms=200.0,
        metrics=Metrics(),
    )
    assert e1.call_id != e2.call_id


def test_singleton_get_prompt_recorder():
    tmpdir = tempfile.mkdtemp()
    pr1 = get_prompt_recorder(tmpdir)
    pr2 = get_prompt_recorder()
    assert pr1 is pr2
    pr3 = get_prompt_recorder(output_dir=None)
    assert pr1 is pr3


def test_call_context_flows_through_agents():
    cfg = LLMBackendConfig(backend="mock", model="test", mock_response="fixed")
    calls = []
    llm = LLMClient.from_config(cfg, on_call_record=lambda d: calls.append(d))

    from backend.assef.agents import RedTeamAgent
    from backend.assef.models import GameRules

    ra = RedTeamAgent(llm, GameRules(max_arena_rounds=5))
    llm.set_call_context({"caller": "red_team", "round": 1})
    llm.chat([{"role": "user", "content": "test"}])
    assert len(calls) == 1
    assert calls[0]["call_context"]["caller"] == "red_team"
