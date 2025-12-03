import contextlib
import json
from unittest.mock import mock_open, patch

import pytest

from browser_utils.script_manager import ScriptManager


@pytest.fixture
def script_manager():
    return ScriptManager(script_dir="test_scripts")


def test_init(script_manager):
    """Test ScriptManager initialization with script directory."""
    assert script_manager.script_dir == "test_scripts"
    assert script_manager.loaded_scripts == {}
    assert script_manager.model_configs == {}


@pytest.mark.parametrize(
    "file_exists,file_content,read_side_effect,expected_result,test_id",
    [
        (True, "console.log('hello');", None, "console.log('hello');", "success"),
        (False, None, None, None, "not_found"),
        (True, None, Exception("Read error"), None, "error"),
    ],
)
def test_load_script(
    script_manager,
    file_exists,
    file_content,
    read_side_effect,
    expected_result,
    test_id,
):
    """Test script loading handles success, file not found, and read errors."""
    patches = [patch("os.path.exists", return_value=file_exists)]

    if file_exists and read_side_effect:
        patches.append(patch("builtins.open", side_effect=read_side_effect))  # type: ignore[arg-type]
    elif file_exists:
        patches.append(patch("builtins.open", mock_open(read_data=file_content)))  # type: ignore[arg-type]

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)

        content = script_manager.load_script("test.js")
        assert content == expected_result

        if expected_result is not None:
            assert script_manager.loaded_scripts["test.js"] == content


@pytest.mark.parametrize(
    "file_exists,config_data,read_side_effect,expected_result,test_id",
    [
        (
            True,
            {"models": [{"name": "model1"}]},
            None,
            [{"name": "model1"}],
            "success",
        ),
        (False, None, None, None, "not_found"),
        (True, {"models": []}, Exception("Read error"), None, "error"),
    ],
)
def test_load_model_config(
    script_manager, file_exists, config_data, read_side_effect, expected_result, test_id
):
    """Test model config loading handles success, file not found, and read errors."""
    patches = [patch("os.path.exists", return_value=file_exists)]

    if file_exists and read_side_effect:
        patches.append(patch("builtins.open", side_effect=read_side_effect))  # type: ignore[arg-type]
    elif file_exists:
        json_data = json.dumps(config_data)
        patches.append(patch("builtins.open", mock_open(read_data=json_data)))  # type: ignore[arg-type]

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)

        models = script_manager.load_model_config("config.json")
        assert models == expected_result

        if expected_result is not None:
            assert script_manager.model_configs["config.json"] == expected_result


def test_generate_dynamic_script_success(script_manager):
    """Test dynamic script generation with model injection."""
    base_script = """
    // Some code
    const MODELS_TO_INJECT = [
        { name: 'old', displayName: 'Old', description: 'Old desc' }
    ];
    // More code
    """

    models = [{"name": "new", "displayName": "New", "description": "New desc"}]

    generated_script = script_manager.generate_dynamic_script(base_script, models, "v1")

    assert "name: 'new'" in generated_script
    assert "displayName: `New (Script v1)`" in generated_script
    assert "description: `New desc`" in generated_script
    assert "name: 'old'" not in generated_script


def test_generate_dynamic_script_marker_not_found(script_manager):
    """Test script generation returns original when marker not found."""
    base_script = "console.log('no markers');"
    models = [{"name": "new"}]

    generated_script = script_manager.generate_dynamic_script(base_script, models)

    assert generated_script == base_script


def test_generate_dynamic_script_end_marker_not_found(script_manager):
    """Test script generation when end marker is missing."""
    base_script = "const MODELS_TO_INJECT = ["
    models = [{"name": "new"}]

    # It seems the logic searches for matching brackets
    # If not found, it might fail or return partial
    # Wait, the code says:
    # if start_idx == -1: return base_script
    # for i in range(end_idx, len(base_script)): ...
    # if found_end ...
    # If loop finishes without found_end, it proceeds to replace using end_idx?
    # Let's check implementation behavior

    # In generate_dynamic_script:
    # if not found_end: logger.warning("..."); return base_script
    # I should check the implementation in file

    pass
    # Let's look at lines 103+ of browser_utils/script_manager.py to see what happens if end not found

    # Based on implementation: if not found_end, return base_script
    generated_script = script_manager.generate_dynamic_script(base_script, models)
    assert generated_script == base_script  # Should return original when end not found


def test_generate_dynamic_script_nested_brackets(script_manager):
    """Test generate_dynamic_script handles nested brackets correctly."""
    base_script = """
    const MODELS_TO_INJECT = [
        { data: [1, 2, 3] },
        { data: [4, 5, 6] }
    ];
    """
    models = [{"name": "new", "displayName": "New"}]

    generated_script = script_manager.generate_dynamic_script(base_script, models)

    # Should successfully replace despite nested brackets (lines 95, 101)
    assert "name: 'new'" in generated_script


def test_generate_dynamic_script_exception(script_manager):
    """Test generate_dynamic_script handles exceptions gracefully."""
    base_script = """
    const MODELS_TO_INJECT = [
        { name: 'old', displayName: 'Old' }
    ];
    """
    models = [{"name": "new", "displayName": "New"}]

    # Mock logger to raise exception during logger.info call
    with patch("browser_utils.script_manager.logger") as mock_logger:
        # Make logger.info raise an exception to trigger except block (lines 126-128)
        mock_logger.info.side_effect = RuntimeError("Simulated error during logging")

        # Should catch exception and return base_script
        generated_script = script_manager.generate_dynamic_script(
            base_script, models, "v1"
        )

        # Verify exception handler was triggered (line 127)
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        assert "生成动态脚本失败" in error_call
        assert "Simulated error during logging" in error_call

        # Should return original base_script (line 128)
        assert generated_script == base_script
        assert "old" in generated_script  # Original content preserved


@pytest.mark.asyncio
async def test_inject_script_to_page_success(script_manager):
    """Test inject_script_to_page successfully injects script."""
    from unittest.mock import AsyncMock

    page = AsyncMock()
    page.add_init_script = AsyncMock()

    script_content = """
    // ==UserScript==
    // @name Test
    // ==/UserScript==
    console.log('test');
    """

    result = await script_manager.inject_script_to_page(page, script_content, "test.js")

    # Should return True and call add_init_script (lines 128-135)
    assert result is True
    page.add_init_script.assert_called_once()

    # Verify UserScript headers were cleaned
    call_args = page.add_init_script.call_args[0][0]
    assert "==UserScript==" not in call_args
    assert "console.log('test');" in call_args


@pytest.mark.asyncio
async def test_inject_script_to_page_exception(script_manager):
    """Test inject_script_to_page handles exceptions."""
    from unittest.mock import AsyncMock

    page = AsyncMock()
    page.add_init_script = AsyncMock(side_effect=Exception("Injection failed"))

    script_content = "console.log('test');"

    result = await script_manager.inject_script_to_page(page, script_content)

    # Should return False on exception (lines 137-139)
    assert result is False


def test_clean_userscript_headers(script_manager):
    """Test _clean_userscript_headers removes UserScript metadata."""
    script_with_headers = """// ==UserScript==
// @name         Test Script
// @version      1.0
// @description  Test
// ==/UserScript==

console.log('actual code');
const x = 5;
"""

    cleaned = script_manager._clean_userscript_headers(script_with_headers)

    # Should remove all UserScript header lines (lines 143-159)
    assert "==UserScript==" not in cleaned
    assert "@name" not in cleaned
    assert "@version" not in cleaned
    assert "==/UserScript==" not in cleaned
    assert "console.log('actual code');" in cleaned
    assert "const x = 5;" in cleaned


def test_clean_userscript_headers_no_headers(script_manager):
    """Test _clean_userscript_headers with script that has no headers."""
    script_no_headers = "console.log('test');\nconst y = 10;"

    cleaned = script_manager._clean_userscript_headers(script_no_headers)

    # Should return unchanged
    assert cleaned == script_no_headers


@pytest.mark.asyncio
async def test_setup_model_injection_success(script_manager):
    """Test setup_model_injection successfully injects script."""
    from unittest.mock import AsyncMock

    page = AsyncMock()
    page.add_init_script = AsyncMock()

    script_content = "console.log('models');"

    with (
        patch("os.path.exists", return_value=True),
        patch("builtins.open", mock_open(read_data=script_content)),
    ):
        result = await script_manager.setup_model_injection(page, "more_models.js")

        # Should return True (lines 166-179)
        assert result is True
        page.add_init_script.assert_called_once()


@pytest.mark.asyncio
async def test_setup_model_injection_file_not_found(script_manager):
    """Test setup_model_injection when script file doesn't exist."""
    from unittest.mock import AsyncMock

    page = AsyncMock()

    with patch("os.path.exists", return_value=False):
        result = await script_manager.setup_model_injection(page, "missing.js")

        # Should return False silently (lines 167-169)
        assert result is False


@pytest.mark.asyncio
async def test_setup_model_injection_load_fails(script_manager):
    """Test setup_model_injection when load_script fails."""
    from unittest.mock import AsyncMock

    page = AsyncMock()

    with (
        patch("os.path.exists", return_value=True),
        patch("builtins.open", side_effect=Exception("Load error")),
    ):
        result = await script_manager.setup_model_injection(page, "broken.js")

        # Should return False when load_script returns None (lines 175-176)
        assert result is False
