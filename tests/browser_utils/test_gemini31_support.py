"""
Unit tests for Gemini 3.1 model support.

Required test categories coverage note:
- Happy path: Covered via Gemini 3.1 Pro normalization + capability matching.
- Null/undefined/empty: Covered in tests/test_smart_rotation_fix.py; omitted here to avoid duplicate coverage.
- Boundary values: N/A (string normalization does not have numeric boundaries).
- Invalid type/malformed: N/A (function expects str; invalid types not used in production paths).
- Error conditions: N/A (pure functions without error branches).
- Concurrency/timing: N/A (no async/concurrency logic).
- Performance: N/A (simple string operations).
- Security-focused: N/A (no auth/permission logic).
"""

import pytest

from api_utils.routers.model_capabilities import _get_model_capabilities
from browser_utils.auth_rotation import _normalize_model_id


class TestNormalizeModelIdGemini31:
    """Tests for _normalize_model_id covering Gemini 3.1 variants."""

    @pytest.mark.parametrize(
        "input_id,expected",
        [
            ("gemini-3.1-pro", "gemini-3.1-pro"),
            ("gemini-3-1-pro", "gemini-3.1-pro"),
            ("gemini-3.1-pro-preview", "gemini-3.1-pro"),
        ],
        ids=[
            "pro-dot",
            "pro-hyphen",
            "pro-preview",
        ],
    )
    def test_normalize_gemini31_variants(self, input_id, expected):
        """Happy path: Normalize supported Gemini 3.1 inputs."""
        # Arrange
        model_id = input_id

        # Act
        result = _normalize_model_id(model_id)

        # Assert
        assert result == expected

    @pytest.mark.parametrize(
        "input_id,expected",
        [
            ("gemini3.1pro", "gemini3-1pro"),
        ],
        ids=["no-separators-pro"],
    )
    def test_normalize_gemini31_edge_formats(self, input_id, expected):
        """Edge cases: Inputs without separators are normalized by dot replacement."""
        # Arrange
        model_id = input_id

        # Act
        result = _normalize_model_id(model_id)

        # Assert
        assert result == expected

    @pytest.mark.parametrize(
        "input_id,expected",
        [
            ("gemini-1.5-pro", "gemini-1.5-pro"),
            ("gemini-2.5-pro", "gemini-2.5-pro"),
            ("gemini-3-pro-preview", "gemini-3-pro-preview"),
        ],
        ids=["gemini-1-5-pro", "gemini-2-5-pro", "gemini-3-pro-preview"],
    )
    def test_normalize_existing_models_still_supported(self, input_id, expected):
        """Regression: Existing model normalizations still map correctly."""
        # Arrange
        model_id = input_id

        # Act
        result = _normalize_model_id(model_id)

        # Assert
        assert result == expected


class TestModelCapabilitiesGemini31:
    """Tests for _get_model_capabilities for Gemini 3.1 models."""

    @pytest.mark.parametrize(
        "model_id",
        [
            "gemini-3.1-pro",
            "gemini-3.1-pro-preview",
            "gemini3.1pro-exp",
        ],
        ids=["pro", "pro-preview", "pro-compact"],
    )
    def test_gemini31_pro_capabilities(self, model_id):
        """Happy path: Gemini 3.1 Pro maps to gemini3Pro category."""
        # Arrange
        expected_levels = ["low", "high"]

        # Act
        result = _get_model_capabilities(model_id)

        # Assert
        assert result["thinkingType"] == "level"
        assert result["levels"] == expected_levels
        assert result["defaultLevel"] == "high"
        assert result["supportsGoogleSearch"] is True
