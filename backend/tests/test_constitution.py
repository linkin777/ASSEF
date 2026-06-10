import pytest
from assef.models import Constitution


class TestConstitution:
    def test_default_returns_valid_instance(self):
        c = Constitution.default()
        assert isinstance(c.preamble, str)
        assert len(c.preamble) > 0
        assert isinstance(c.attack_success_criteria, str)
        assert len(c.attack_success_criteria) > 0
        assert isinstance(c.fix_success_criteria, str)
        assert len(c.fix_success_criteria) > 0
        assert isinstance(c.scoring_rules, str)
        assert len(c.scoring_rules) > 0
        assert isinstance(c.constraints, str)
        assert len(c.constraints) > 0

    def test_custom_constitution(self):
        c = Constitution(
            preamble="test",
            attack_success_criteria="test",
            fix_success_criteria="test",
            scoring_rules="test",
            constraints="test",
        )
        assert c.preamble == "test"
