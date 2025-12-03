"""
High-quality tests for browser_utils/thinking_normalizer.py (minimal mocking).

Focus: Test real normalization logic with minimal mocks.
Note: Some tests mock DEFAULT_THINKING_BUDGET and ENABLE_THINKING_BUDGET for predictability.
"""

from unittest.mock import patch


def test_normalize_reasoning_effort_none_uses_default():
    """
    测试场景: reasoning_effort 为 None，使用默认配置
    策略: Mock 配置值，测试默认行为
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    with (
        patch("browser_utils.thinking_normalizer.ENABLE_THINKING_BUDGET", True),
        patch("browser_utils.thinking_normalizer.DEFAULT_THINKING_BUDGET", 10000),
    ):
        result = normalize_reasoning_effort(None)

        assert result.thinking_enabled is True
        assert result.budget_enabled is True
        assert result.budget_value == 10000
        assert result.original_value is None


def test_normalize_reasoning_effort_zero_disables():
    """
    测试场景: reasoning_effort = 0 关闭思考模式
    验证: thinking_enabled = False
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort(0)

    assert result.thinking_enabled is False
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == 0


def test_normalize_reasoning_effort_string_zero_disables():
    """
    测试场景: reasoning_effort = "0" (字符串) 关闭思考模式
    验证: 字符串 "0" 也能正确处理
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("0")

    assert result.thinking_enabled is False
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == "0"


def test_normalize_reasoning_effort_none_string_no_budget():
    """
    测试场景: reasoning_effort = "none" 开启思考，不限预算
    验证: thinking_enabled = True, budget_enabled = False
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("none")

    assert result.thinking_enabled is True
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == "none"


def test_normalize_reasoning_effort_minus_one_string_no_budget():
    """
    测试场景: reasoning_effort = "-1" (字符串) 开启思考，不限预算
    验证: 字符串 "-1" 等价于 "none"
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("-1")

    assert result.thinking_enabled is True
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == "-1"


def test_normalize_reasoning_effort_minus_one_int_no_budget():
    """
    测试场景: reasoning_effort = -1 (整数) 开启思考，不限预算
    验证: 整数 -1 等价于 "none"
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort(-1)

    assert result.thinking_enabled is True
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == -1


def test_normalize_reasoning_effort_preset_low():
    """
    测试场景: reasoning_effort = "low" (预设值)
    验证: thinking_enabled = True, budget_enabled = False (由 _should_enable_from_raw 确定)
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("low")

    assert result.thinking_enabled is True
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == "low"


def test_normalize_reasoning_effort_preset_medium():
    """
    测试场景: reasoning_effort = "medium" (预设值)
    验证: thinking_enabled = True, budget_enabled = False (由 _should_enable_from_raw 确定)
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("medium")

    assert result.thinking_enabled is True
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == "medium"


def test_normalize_reasoning_effort_preset_high():
    """
    测试场景: reasoning_effort = "high" (预设值)
    验证: thinking_enabled = True, budget_enabled = False (由 _should_enable_from_raw 确定)
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("high")

    assert result.thinking_enabled is True
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == "high"


def test_normalize_reasoning_effort_positive_integer():
    """
    测试场景: reasoning_effort = 5000 (正整数预算)
    验证: 开启思考并设置具体预算值
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort(5000)

    assert result.thinking_enabled is True
    assert result.budget_enabled is True
    assert result.budget_value == 5000
    assert result.original_value == 5000


def test_normalize_reasoning_effort_string_number():
    """
    测试场景: reasoning_effort = "8000" (字符串数字)
    验证: 字符串数字被正确解析
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("8000")

    assert result.thinking_enabled is True
    assert result.budget_enabled is True
    assert result.budget_value == 8000
    assert result.original_value == "8000"


def test_normalize_reasoning_effort_invalid_string_uses_default():
    """
    测试场景: reasoning_effort = "invalid" (无效字符串)
    验证: 使用默认配置
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    with patch("browser_utils.thinking_normalizer.ENABLE_THINKING_BUDGET", False):
        result = normalize_reasoning_effort("invalid")

        assert result.thinking_enabled is False
        assert result.budget_enabled is False
        assert result.budget_value is None
        assert result.original_value == "invalid"


def test_normalize_reasoning_effort_negative_number_uses_default():
    """
    测试场景: reasoning_effort = -5 (负数，非 -1)
    验证: 使用默认配置
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    with (
        patch("browser_utils.thinking_normalizer.ENABLE_THINKING_BUDGET", True),
        patch("browser_utils.thinking_normalizer.DEFAULT_THINKING_BUDGET", 10000),
    ):
        result = normalize_reasoning_effort(-5)

        assert result.thinking_enabled is True
        assert result.budget_enabled is True
        assert result.budget_value == 10000
        assert result.original_value == -5


def test_normalize_reasoning_effort_case_insensitive():
    """
    测试场景: reasoning_effort 字符串大小写不敏感
    验证: "NONE", "None", "none" 都被正确处理
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    for value in ["NONE", "None", "none"]:
        result = normalize_reasoning_effort(value)
        assert result.thinking_enabled is True
        assert result.budget_enabled is False
        assert result.original_value == value


def test_parse_budget_value_positive_int():
    """
    测试场景: _parse_budget_value 解析正整数
    验证: 返回原始整数值
    """
    from browser_utils.thinking_normalizer import _parse_budget_value

    assert _parse_budget_value(1000) == 1000
    assert _parse_budget_value(5000) == 5000
    assert _parse_budget_value(1) == 1


def test_parse_budget_value_zero_returns_none():
    """
    测试场景: _parse_budget_value 解析 0
    验证: 0 不是有效预算，返回 None
    """
    from browser_utils.thinking_normalizer import _parse_budget_value

    assert _parse_budget_value(0) is None


def test_parse_budget_value_negative_returns_none():
    """
    测试场景: _parse_budget_value 解析负数
    验证: 负数不是有效预算，返回 None
    """
    from browser_utils.thinking_normalizer import _parse_budget_value

    assert _parse_budget_value(-100) is None
    assert _parse_budget_value(-1) is None


def test_parse_budget_value_string_number():
    """
    测试场景: _parse_budget_value 解析字符串数字
    验证: "1000" → 1000
    """
    from browser_utils.thinking_normalizer import _parse_budget_value

    assert _parse_budget_value("1000") == 1000
    assert _parse_budget_value("5000") == 5000


def test_parse_budget_value_string_with_whitespace():
    """
    测试场景: _parse_budget_value 解析带空格的字符串
    验证: "  1000  " → 1000 (trim 后解析)
    """
    from browser_utils.thinking_normalizer import _parse_budget_value

    assert _parse_budget_value("  1000  ") == 1000


def test_parse_budget_value_invalid_string():
    """
    测试场景: _parse_budget_value 解析无效字符串
    验证: 返回 None
    """
    from browser_utils.thinking_normalizer import _parse_budget_value

    assert _parse_budget_value("invalid") is None
    assert _parse_budget_value("abc123") is None
    assert _parse_budget_value("") is None


def test_format_directive_log_disabled():
    """
    测试场景: 格式化日志（思考模式关闭）
    验证: 日志包含 "关闭思考模式"
    """
    from browser_utils.thinking_normalizer import (
        ThinkingDirective,
        format_directive_log,
    )

    directive = ThinkingDirective(
        thinking_enabled=False,
        budget_enabled=False,
        budget_value=None,
        original_value=0,
    )

    log = format_directive_log(directive)

    assert "关闭思考模式" in log
    assert "原始值: 0" in log


def test_format_directive_log_enabled_with_budget():
    """
    测试场景: 格式化日志（思考模式开启，有预算限制）
    验证: 日志包含预算值
    """
    from browser_utils.thinking_normalizer import (
        ThinkingDirective,
        format_directive_log,
    )

    directive = ThinkingDirective(
        thinking_enabled=True,
        budget_enabled=True,
        budget_value=8000,
        original_value="medium",
    )

    log = format_directive_log(directive)

    assert "开启思考并限制预算" in log
    assert "8000 tokens" in log
    assert "原始值: medium" in log


def test_format_directive_log_enabled_no_budget():
    """
    测试场景: 格式化日志（思考模式开启，不限预算）
    验证: 日志包含 "不限制预算"
    """
    from browser_utils.thinking_normalizer import (
        ThinkingDirective,
        format_directive_log,
    )

    directive = ThinkingDirective(
        thinking_enabled=True,
        budget_enabled=False,
        budget_value=None,
        original_value="none",
    )

    log = format_directive_log(directive)

    assert "开启思考，不限制预算" in log
    assert "原始值: none" in log
