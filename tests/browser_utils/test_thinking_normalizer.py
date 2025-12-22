"""
High-quality tests for browser_utils/thinking_normalizer.py (minimal mocking).

Focus: Test real normalization logic with minimal mocks.
Note: Some tests mock DEFAULT_THINKING_BUDGET and ENABLE_THINKING_BUDGET for predictability.
"""

from unittest.mock import patch


def test_normalize_reasoning_effort_none_uses_default():
    """
    Test scenario: reasoning_effort is None, use default configuration
    Strategy: Mock configuration values, test default behavior
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
    Test scenario: reasoning_effort = 0 disables thinking mode
    Verify: thinking_enabled = False
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort(0)

    assert result.thinking_enabled is False
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == 0


def test_normalize_reasoning_effort_string_zero_disables():
    """
    Test scenario: reasoning_effort = "0" (string) disables thinking mode
    Verify: String "0" is also handled correctly
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("0")

    assert result.thinking_enabled is False
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == "0"


def test_normalize_reasoning_effort_none_string_no_budget():
    """
    Test scenario: reasoning_effort = "none" enables thinking, no budget limit
    Verify: thinking_enabled = True, budget_enabled = False
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("none")

    assert result.thinking_enabled is True
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == "none"


def test_normalize_reasoning_effort_minus_one_string_no_budget():
    """
    Test scenario: reasoning_effort = "-1" (string) enables thinking, no budget limit
    Verify: String "-1" is equivalent to "none"
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("-1")

    assert result.thinking_enabled is True
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == "-1"


def test_normalize_reasoning_effort_minus_one_int_no_budget():
    """
    Test scenario: reasoning_effort = -1 (integer) enables thinking, no budget limit
    Verify: Integer -1 is equivalent to "none"
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort(-1)

    assert result.thinking_enabled is True
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == -1


def test_normalize_reasoning_effort_preset_low():
    """
    Test scenario: reasoning_effort = "low" (preset value)
    Verify: thinking_enabled = True, budget_enabled = False (determined by _should_enable_from_raw)
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("low")

    assert result.thinking_enabled is True
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == "low"


def test_normalize_reasoning_effort_preset_medium():
    """
    Test scenario: reasoning_effort = "medium" (preset value)
    Verify: thinking_enabled = True, budget_enabled = False (determined by _should_enable_from_raw)
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("medium")

    assert result.thinking_enabled is True
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == "medium"


def test_normalize_reasoning_effort_preset_high():
    """
    Test scenario: reasoning_effort = "high" (preset value)
    Verify: thinking_enabled = True, budget_enabled = False (determined by _should_enable_from_raw)
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("high")

    assert result.thinking_enabled is True
    assert result.budget_enabled is False
    assert result.budget_value is None
    assert result.original_value == "high"


def test_normalize_reasoning_effort_positive_integer():
    """
    Test scenario: reasoning_effort = 5000 (positive integer budget)
    Verify: Enable thinking and set specific budget value
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort(5000)

    assert result.thinking_enabled is True
    assert result.budget_enabled is True
    assert result.budget_value == 5000
    assert result.original_value == 5000


def test_normalize_reasoning_effort_string_number():
    """
    Test scenario: reasoning_effort = "8000" (string number)
    Verify: String number correctly parsed
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    result = normalize_reasoning_effort("8000")

    assert result.thinking_enabled is True
    assert result.budget_enabled is True
    assert result.budget_value == 8000
    assert result.original_value == "8000"


def test_normalize_reasoning_effort_invalid_string_uses_default():
    """
    Test scenario: reasoning_effort = "invalid" (invalid string)
    Verify: Use default configuration
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
    Test scenario: reasoning_effort = -5 (negative number, not -1)
    Verify: Use default configuration
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
    Test scenario: reasoning_effort string is case-insensitive
    Verify: "NONE", "None", "none" are all correctly handled
    """
    from browser_utils.thinking_normalizer import normalize_reasoning_effort

    for value in ["NONE", "None", "none"]:
        result = normalize_reasoning_effort(value)
        assert result.thinking_enabled is True
        assert result.budget_enabled is False
        assert result.original_value == value


def test_parse_budget_value_positive_int():
    """
    Test scenario: _parse_budget_value parses positive integer
    Verify: Return original integer value
    """
    from browser_utils.thinking_normalizer import _parse_budget_value

    assert _parse_budget_value(1000) == 1000
    assert _parse_budget_value(5000) == 5000
    assert _parse_budget_value(1) == 1


def test_parse_budget_value_zero_returns_none():
    """
    Test scenario: _parse_budget_value parses 0
    Verify: 0 is not a valid budget, return None
    """
    from browser_utils.thinking_normalizer import _parse_budget_value

    assert _parse_budget_value(0) is None


def test_parse_budget_value_negative_returns_none():
    """
    Test scenario: _parse_budget_value parses negative number
    Verify: Negative number is not a valid budget, return None
    """
    from browser_utils.thinking_normalizer import _parse_budget_value

    assert _parse_budget_value(-100) is None
    assert _parse_budget_value(-1) is None


def test_parse_budget_value_string_number():
    """
    Test scenario: _parse_budget_value parses string number
    Verify: "1000" → 1000
    """
    from browser_utils.thinking_normalizer import _parse_budget_value

    assert _parse_budget_value("1000") == 1000
    assert _parse_budget_value("5000") == 5000


def test_parse_budget_value_string_with_whitespace():
    """
    Test scenario: _parse_budget_value parses string with whitespace
    Verify: "  1000  " → 1000 (parse after trimming)
    """
    from browser_utils.thinking_normalizer import _parse_budget_value

    assert _parse_budget_value("  1000  ") == 1000


def test_parse_budget_value_invalid_string():
    """
    Test scenario: _parse_budget_value parses invalid string
    Verify: Return None
    """
    from browser_utils.thinking_normalizer import _parse_budget_value

    assert _parse_budget_value("invalid") is None
    assert _parse_budget_value("abc123") is None
    assert _parse_budget_value("") is None


def test_format_directive_log_disabled():
    """
    Test scenario: Format log (thinking mode disabled)
    Verify: Log contains "Disabling thinking mode"
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

    assert "Disabling thinking mode" in log
    assert "Original value: 0" in log


def test_format_directive_log_enabled_with_budget():
    """
    Test scenario: Format log (thinking mode enabled, with budget limit)
    Verify: Log contains budget value
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

    assert "Enabling thinking with budget limit" in log
    assert "8000 tokens" in log
    assert "Original value: medium" in log


def test_format_directive_log_enabled_no_budget():
    """
    Test scenario: Format log (thinking mode enabled, no budget limit)
    Verify: Log contains "no budget limit"
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

    assert "Enabling thinking, no budget limit" in log
    assert "Original value: none" in log
