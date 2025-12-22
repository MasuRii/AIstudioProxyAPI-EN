"""
High-quality tests for api_utils/common_utils.py - Random ID generation.

Focus: Test random_id function with various lengths and verify output format.
Strategy: Test default/custom lengths, character set, uniqueness.
"""

import re

from api_utils.common_utils import random_id


def test_random_id_default_length():
    """
    Test scenario: Generate random ID with default length
    Expected: Return 24-character string (lines 5-6)
    """
    result = random_id()

    # Verify: Length is 24
    assert len(result) == 24

    # Verify: Only contains lowercase letters and numbers
    assert re.match(r"^[a-z0-9]+$", result)


def test_random_id_custom_length_short():
    """
    Test scenario: Generate random ID with short length (5)
    Expected: Return 5-character string
    """
    result = random_id(5)

    # Verify: Length is 5
    assert len(result) == 5

    # Verify: Only contains lowercase letters and numbers
    assert re.match(r"^[a-z0-9]+$", result)


def test_random_id_custom_length_long():
    """
    Test scenario: Generate random ID with long length (100)
    Expected: Return 100-character string
    """
    result = random_id(100)

    # Verify: Length is 100
    assert len(result) == 100

    # Verify: Only contains lowercase letters and numbers
    assert re.match(r"^[a-z0-9]+$", result)


def test_random_id_length_one():
    """
    Test scenario: Generate random ID with length 1
    Expected: Return 1-character string
    """
    result = random_id(1)

    # Verify: Length is 1
    assert len(result) == 1

    # Verify: Character is a lowercase letter or number
    assert result in "abcdefghijklmnopqrstuvwxyz0123456789"


def test_random_id_length_zero():
    """
    Test scenario: Generate random ID with length 0
    Expected: Return empty string
    """
    result = random_id(0)

    # Verify: Empty string
    assert result == ""
    assert len(result) == 0


def test_random_id_character_set():
    """
    Test scenario: Verify character set only contains lowercase letters and numbers
    Expected: Does not contain uppercase letters, special characters, or spaces (line 5)
    """
    result = random_id(50)

    # Verify: Each character is in the expected character set
    charset = "abcdefghijklmnopqrstuvwxyz0123456789"
    for char in result:
        assert char in charset


def test_random_id_uniqueness():
    """
    Test scenario: Multiple calls return different values
    Expected: Generated IDs have high uniqueness
    """
    results = [random_id() for _ in range(100)]

    # Verify: 100 calls have at least 95 different values (considering minimal probability of collision)
    unique_results = set(results)
    assert len(unique_results) >= 95


def test_random_id_no_uppercase():
    """
    Test scenario: Verify no uppercase letters included
    Expected: Output does not contain A-Z
    """
    result = random_id(50)

    # Verify: No uppercase letters
    assert not any(char.isupper() for char in result)


def test_random_id_no_special_characters():
    """
    Test scenario: Verify no special characters included
    Expected: Output only contains alphanumeric characters
    """
    result = random_id(50)

    # Verify: Is alphanumeric
    assert result.isalnum()

    # Verify: No spaces, punctuation, or other special characters
    assert not any(not char.isalnum() for char in result)


def test_random_id_multiple_calls_different_values():
    """
    Test scenario: Consecutive calls should return different values
    Expected: Two calls return different IDs (high probability)
    """
    id1 = random_id()
    id2 = random_id()

    # Verify: Extremely high probability of being different (theoretically could be same but probability is very low)
    assert id1 != id2
