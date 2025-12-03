"""
High-quality tests for api_utils/common_utils.py - Random ID generation.

Focus: Test random_id function with various lengths and verify output format.
Strategy: Test default/custom lengths, character set, uniqueness.
"""

import re

from api_utils.common_utils import random_id


def test_random_id_default_length():
    """
    测试场景: 使用默认长度生成随机 ID
    预期: 返回 24 字符长度的字符串 (lines 5-6)
    """
    result = random_id()

    # 验证: 长度为 24
    assert len(result) == 24

    # 验证: 只包含小写字母和数字
    assert re.match(r"^[a-z0-9]+$", result)


def test_random_id_custom_length_short():
    """
    测试场景: 使用短长度 (5) 生成随机 ID
    预期: 返回 5 字符长度的字符串
    """
    result = random_id(5)

    # 验证: 长度为 5
    assert len(result) == 5

    # 验证: 只包含小写字母和数字
    assert re.match(r"^[a-z0-9]+$", result)


def test_random_id_custom_length_long():
    """
    测试场景: 使用长长度 (100) 生成随机 ID
    预期: 返回 100 字符长度的字符串
    """
    result = random_id(100)

    # 验证: 长度为 100
    assert len(result) == 100

    # 验证: 只包含小写字母和数字
    assert re.match(r"^[a-z0-9]+$", result)


def test_random_id_length_one():
    """
    测试场景: 生成长度为 1 的随机 ID
    预期: 返回 1 字符长度的字符串
    """
    result = random_id(1)

    # 验证: 长度为 1
    assert len(result) == 1

    # 验证: 字符是小写字母或数字
    assert result in "abcdefghijklmnopqrstuvwxyz0123456789"


def test_random_id_length_zero():
    """
    测试场景: 生成长度为 0 的随机 ID
    预期: 返回空字符串
    """
    result = random_id(0)

    # 验证: 空字符串
    assert result == ""
    assert len(result) == 0


def test_random_id_character_set():
    """
    测试场景: 验证字符集只包含小写字母和数字
    预期: 不包含大写字母、特殊字符或空格 (line 5)
    """
    result = random_id(50)

    # 验证: 每个字符都在预期字符集中
    charset = "abcdefghijklmnopqrstuvwxyz0123456789"
    for char in result:
        assert char in charset


def test_random_id_uniqueness():
    """
    测试场景: 多次调用返回不同的值
    预期: 生成的 ID 具有高度唯一性
    """
    results = [random_id() for _ in range(100)]

    # 验证: 100 次调用至少有 95 个不同的值 (考虑极小概率碰撞)
    unique_results = set(results)
    assert len(unique_results) >= 95


def test_random_id_no_uppercase():
    """
    测试场景: 验证不包含大写字母
    预期: 输出不包含 A-Z
    """
    result = random_id(50)

    # 验证: 没有大写字母
    assert not any(char.isupper() for char in result)


def test_random_id_no_special_characters():
    """
    测试场景: 验证不包含特殊字符
    预期: 输出只包含字母数字
    """
    result = random_id(50)

    # 验证: 是字母数字
    assert result.isalnum()

    # 验证: 没有空格、标点或其他特殊字符
    assert not any(not char.isalnum() for char in result)


def test_random_id_multiple_calls_different_values():
    """
    测试场景: 连续调用应返回不同的值
    预期: 两次调用返回不同的 ID (高概率)
    """
    id1 = random_id()
    id2 = random_id()

    # 验证: 极大概率不同 (理论上可能相同但概率极低)
    assert id1 != id2
