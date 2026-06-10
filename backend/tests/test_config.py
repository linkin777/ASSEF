import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from assef.models.config import (
    Config,
    ConstitutionConfig,
    GameRulesConfig,
    LLMBackendConfig,
    NormalTestConfig,
    SandboxConfig,
    SuccessCriteriaConfig,
    TargetConfig,
    build_target_spec_from_config,
    load_config,
)
from assef.models.target_spec import TargetSpec


VALID_TARGET_DATA = {
    "name": "test-target",
    "description": "Test target",
    "sandbox_type": "process",
    "public_spec": "A simple test target",
    "attack_surface": "user input",
    "success_criteria": {"attack": "flag", "fix": "no flag"},
    "normal_tests": [
        {"name": "test1", "input": {"x": 1}, "expected_output": {"y": 2}}
    ],
}


class TestLLMBackendConfig:
    def test_valid_backend_works(self):
        cfg = LLMBackendConfig(backend="ollama", model="llama3")
        assert cfg.backend == "ollama"
        assert cfg.model == "llama3"

    def test_invalid_backend_raises(self):
        with pytest.raises(ValidationError):
            LLMBackendConfig(backend="invalid-backend")

    def test_all_valid_backends(self):
        for b in ["ollama", "openai", "deepseek", "anthropic", "mock"]:
            cfg = LLMBackendConfig(backend=b)
            assert cfg.backend == b


class TestConfigDefaults:
    """测试 Config 各项默认值：LLM 后端列表、游戏规则、沙箱、宪法。"""

    def test_default_config(self):
        cfg = Config()
        assert cfg.llm_backends == []
        assert isinstance(cfg.game_rules, GameRulesConfig)
        assert isinstance(cfg.constitution, ConstitutionConfig)
        assert isinstance(cfg.sandbox, SandboxConfig)
        assert cfg.targets == []

    def test_default_game_rules_values(self):
        cfg = Config()
        gr = cfg.game_rules
        assert gr.max_blue_retries == 2
        assert gr.performance_degrade_limit == 1.5
        assert gr.code_bloat_limit == 2.0
        assert gr.red_strategy_mutation_threshold == 3
        assert gr.max_arena_rounds == 10
        assert gr.self_adversary_attempts == 3
        assert gr.blue_self_iteration_limit == 3
        assert gr.red_max_plans_early == 3
        assert gr.red_max_plans_late == 1

    def test_default_sandbox_values(self):
        cfg = Config()
        s = cfg.sandbox
        assert s.timeout == 30.0
        assert "os.system" in s.dangerous_patterns
        assert "subprocess" in s.dangerous_patterns

    def test_default_constitution_values(self):
        cfg = Config()
        c = cfg.constitution
        assert "ASSEF" in c.preamble
        assert "攻击成功判定" in c.attack_success_criteria
        assert "修复成功判定" in c.fix_success_criteria
        assert "红蓝加减分" in c.scoring_rules
        assert "判官脚本技术约束" in c.constraints


class TestConfigModelValidate:
    """测试 Config.model_validate 对有效数据和无效数据的验证行为。"""

    def test_valid_json_data(self):
        data = {
            "llm_backends": [
                {"backend": "ollama", "model": "llama3"}
            ],
            "targets": [VALID_TARGET_DATA],
        }
        cfg = Config.model_validate(data)
        assert len(cfg.llm_backends) == 1
        assert cfg.llm_backends[0].backend == "ollama"
        assert len(cfg.targets) == 1
        assert cfg.targets[0].name == "test-target"

    def test_missing_optional_fields_defaults(self):
        data = {}
        cfg = Config.model_validate(data)
        assert cfg.llm_backends == []
        assert cfg.targets == []
        assert isinstance(cfg.game_rules, GameRulesConfig)

    def test_invalid_field_type_raises(self):
        with pytest.raises(ValidationError):
            Config.model_validate({"game_rules": "not-a-dict"})

    def test_invalid_backend_in_list_raises(self):
        with pytest.raises(ValidationError):
            Config.model_validate({
                "llm_backends": [{"backend": "not-valid"}]
            })


class TestLoadConfig:
    """测试 load_config 函数：文件不存在返回默认值、有效/无效 JSON 文件的加载行为。"""

    def test_file_not_found_returns_default(self):
        cfg = load_config("/nonexistent/path/config.json")
        assert isinstance(cfg, Config)
        assert cfg.llm_backends == []

    def test_valid_json_file_works(self, tmp_path):
        data = {
            "llm_backends": [
                {"backend": "mock", "model": "test-model"}
            ],
            "targets": [VALID_TARGET_DATA],
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(data), encoding="utf-8")

        cfg = load_config(str(config_path))
        assert len(cfg.llm_backends) == 1
        assert cfg.llm_backends[0].backend == "mock"
        assert len(cfg.targets) == 1

    def test_invalid_json_returns_default(self, tmp_path):
        config_path = tmp_path / "bad.json"
        config_path.write_text("not valid json {{{", encoding="utf-8")

        cfg = load_config(str(config_path))
        assert isinstance(cfg, Config)
        assert cfg.llm_backends == []

    def test_valid_json_but_invalid_schema_returns_default(self, tmp_path):
        config_path = tmp_path / "bad_schema.json"
        config_path.write_text(json.dumps({"game_rules": 123}), encoding="utf-8")

        cfg = load_config(str(config_path))
        assert isinstance(cfg, Config)
        assert cfg.llm_backends == []

    def test_nonexistent_path_returns_default(self, tmp_path):
        cfg = load_config(str(tmp_path / "nonexistent.json"))
        assert isinstance(cfg, Config)
        assert cfg.llm_backends == []


class TestTargetConfig:
    """测试 TargetConfig 模型校验：内联代码、代码路径、两者共存、无效沙箱类型等。"""

    def test_with_inline_code(self):
        data = {
            **VALID_TARGET_DATA,
            "code": "print('hello inline')",
        }
        tc = TargetConfig.model_validate(data)
        assert tc.code == "print('hello inline')"
        assert tc.code_path == ""

    def test_with_code_path(self):
        data = {
            **VALID_TARGET_DATA,
            "code_path": "/some/path/to/target.py",
        }
        tc = TargetConfig.model_validate(data)
        assert tc.code_path == "/some/path/to/target.py"
        assert tc.code == ""

    def test_with_both_code_and_code_path(self):
        data = {
            **VALID_TARGET_DATA,
            "code": "inline",
            "code_path": "/some/path.py",
        }
        tc = TargetConfig.model_validate(data)
        assert tc.code == "inline"
        assert tc.code_path == "/some/path.py"

    def test_invalid_sandbox_type_raises(self):
        with pytest.raises(ValidationError):
            TargetConfig.model_validate({**VALID_TARGET_DATA, "sandbox_type": "kubernetes"})

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            TargetConfig.model_validate({"name": "no-fields"})


class TestBuildTargetSpec:
    """测试 build_target_spec_from_config 将 TargetConfig 转换为 TargetSpec。"""

    def test_with_inline_code(self):
        data = {
            **VALID_TARGET_DATA,
            "code": "print('hello')",
        }
        tc = TargetConfig.model_validate(data)
        spec = build_target_spec_from_config(tc)

        assert isinstance(spec, TargetSpec)
        assert spec.name == "test-target"
        assert spec.code == "print('hello')"
        assert spec.sandbox_type == "process"
        assert spec.success_criteria.attack == "flag"
        assert spec.success_criteria.fix == "no flag"
        assert len(spec.normal_tests) == 1
        assert spec.normal_tests[0].name == "test1"

    def test_with_code_path(self, tmp_path):
        code_file = tmp_path / "target.py"
        code_file.write_text("print('from file')", encoding="utf-8")

        data = {
            **VALID_TARGET_DATA,
            "code_path": str(code_file),
        }
        tc = TargetConfig.model_validate(data)
        spec = build_target_spec_from_config(tc)

        assert spec.code == "print('from file')"

    def test_with_code_path_prioritized(self, tmp_path):
        code_file = tmp_path / "target2.py"
        code_file.write_text("print('from file')", encoding="utf-8")

        data = {
            **VALID_TARGET_DATA,
            "code": "print('inline')",
            "code_path": str(code_file),
        }
        tc = TargetConfig.model_validate(data)
        spec = build_target_spec_from_config(tc)

        assert spec.code == "print('from file')"

    def test_code_path_not_found_raises(self):
        data = {
            **VALID_TARGET_DATA,
            "code_path": "/nonexistent/target.py",
        }
        tc = TargetConfig.model_validate(data)

        with pytest.raises(ValueError, match="读取靶机代码文件失败"):
            build_target_spec_from_config(tc)


class TestGameRulesConfigNewFields:
    """测试 GameRulesConfig 新增字段：blue_self_iteration_limit、red_max_plans_early/late。"""

    def test_blue_self_iteration_limit(self):
        gr = GameRulesConfig()
        assert gr.blue_self_iteration_limit == 3

        gr = GameRulesConfig(blue_self_iteration_limit=5)
        assert gr.blue_self_iteration_limit == 5

    def test_red_max_plans_early(self):
        gr = GameRulesConfig()
        assert gr.red_max_plans_early == 3

        gr = GameRulesConfig(red_max_plans_early=5)
        assert gr.red_max_plans_early == 5

    def test_red_max_plans_late(self):
        gr = GameRulesConfig()
        assert gr.red_max_plans_late == 1

        gr = GameRulesConfig(red_max_plans_late=2)
        assert gr.red_max_plans_late == 2
