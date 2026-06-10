"""测试 TargetSpec 目标靶机规格模型的校验逻辑。"""

import importlib.util
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from assef.models.target_spec import TargetSpec, SuccessCriteria, NormalTest

VALID_DATA = {
    "name": "test-target",
    "description": "测试靶机",
    "sandbox_type": "process",
    "sandbox_spec": {"timeout": 30},
    "code": "print('hello')",
    "public_spec": "输入: name, 输出: result",
    "attack_surface": "name",
    "success_criteria": {"attack": "获取 flag", "fix": "移除后门"},
    "normal_tests": [
        {"name": "正常查询", "input": {"name": "alice"}, "expected_output": {"role": "admin"}}
    ],
}


class TestTargetSpecValid:
    """测试 TargetSpec.model_validate 对有效数据的通过情况。"""

    def test_valid_data_passes(self):
        spec = TargetSpec.model_validate(VALID_DATA)
        assert spec.name == "test-target"
        assert spec.sandbox_type == "process"
        assert isinstance(spec.success_criteria, SuccessCriteria)
        assert isinstance(spec.normal_tests[0], NormalTest)

    def test_valid_data_with_docker_sandbox(self):
        data = {**VALID_DATA, "sandbox_type": "docker"}
        spec = TargetSpec.model_validate(data)
        assert spec.sandbox_type == "docker"

    def test_simple_user_query_example_passes(self):
        example_path = Path(__file__).parent.parent / "examples" / "simple_user_query.py"
        spec_mod = importlib.util.spec_from_file_location("simple_user_query", example_path)
        module = importlib.util.module_from_spec(spec_mod)
        spec_mod.loader.exec_module(module)

        spec = TargetSpec.model_validate(module.SIMPLE_USER_QUERY_DATA)
        assert spec.name == "simple-user-query"
        assert len(spec.normal_tests) == 2


class TestTargetSpecInvalid:
    """测试 TargetSpec.model_validate 对无效数据的拒绝情况。"""

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            TargetSpec.model_validate({"name": "no-fields"})

    def test_invalid_sandbox_type_raises(self):
        with pytest.raises(ValidationError):
            TargetSpec.model_validate({**VALID_DATA, "sandbox_type": "kubernetes"})

    def test_wrong_success_criteria_type_raises(self):
        with pytest.raises(ValidationError):
            TargetSpec.model_validate({**VALID_DATA, "success_criteria": "not-a-dict"})

    def test_wrong_normal_tests_type_raises(self):
        with pytest.raises(ValidationError):
            TargetSpec.model_validate({**VALID_DATA, "normal_tests": "not-a-list"})
