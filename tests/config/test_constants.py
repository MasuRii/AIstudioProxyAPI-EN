"""
High-quality tests for config/constants.py - Constants configuration.

Focus: Test DEFAULT_STOP_SEQUENCES parsing with invalid JSON and TypeError.
Strategy: Use importlib to reload module with mocked environment variables.
"""

import os
import sys
from unittest.mock import patch


def test_default_stop_sequences_invalid_json():
    """
    测试场景: DEFAULT_STOP_SEQUENCES 环境变量包含无效 JSON
    预期: JSONDecodeError 被捕获,回退到空列表 (lines 44-45)
    """
    # 保存原始模块
    original_module = sys.modules.get("config.constants")

    try:
        # 模拟环境变量返回无效 JSON
        with patch.dict(os.environ, {"DEFAULT_STOP_SEQUENCES": "invalid json {["}):
            # 删除已导入的模块
            if "config.constants" in sys.modules:
                del sys.modules["config.constants"]

            # 重新导入以执行异常处理路径
            import config.constants as constants

            # 验证: 回退到空列表 (line 45)
            assert constants.DEFAULT_STOP_SEQUENCES == []
    finally:
        # 恢复原始模块
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]


def test_default_stop_sequences_valid_json():
    """
    测试场景: DEFAULT_STOP_SEQUENCES 环境变量包含有效 JSON
    预期: 成功解析为列表 (line 43)
    """
    # 保存原始模块
    original_module = sys.modules.get("config.constants")

    try:
        # 模拟环境变量返回有效 JSON
        with patch.dict(os.environ, {"DEFAULT_STOP_SEQUENCES": '["stop1", "stop2"]'}):
            # 删除已导入的模块
            if "config.constants" in sys.modules:
                del sys.modules["config.constants"]

            # 重新导入
            import config.constants as constants

            # 验证: 成功解析
            assert constants.DEFAULT_STOP_SEQUENCES == ["stop1", "stop2"]
    finally:
        # 恢复原始模块
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]


def test_default_stop_sequences_empty_default():
    """
    测试场景: DEFAULT_STOP_SEQUENCES 未配置
    预期: 使用空列表默认值 (line 43)
    """
    # 保存原始模块和环境变量
    original_module = sys.modules.get("config.constants")
    original_env = os.environ.get("DEFAULT_STOP_SEQUENCES")

    try:
        # 删除环境变量 (如果存在)
        if "DEFAULT_STOP_SEQUENCES" in os.environ:
            del os.environ["DEFAULT_STOP_SEQUENCES"]

        # 删除已导入的模块
        if "config.constants" in sys.modules:
            del sys.modules["config.constants"]

        # 重新导入
        import config.constants as constants

        # 验证: 默认值为空列表 (os.environ.get returns "[]" as default)
        assert constants.DEFAULT_STOP_SEQUENCES == []
    finally:
        # 恢复环境变量
        if original_env is not None:
            os.environ["DEFAULT_STOP_SEQUENCES"] = original_env
        elif "DEFAULT_STOP_SEQUENCES" in os.environ:
            del os.environ["DEFAULT_STOP_SEQUENCES"]

        # 恢复原始模块
        if original_module is not None:
            sys.modules["config.constants"] = original_module
        elif "config.constants" in sys.modules:
            del sys.modules["config.constants"]
