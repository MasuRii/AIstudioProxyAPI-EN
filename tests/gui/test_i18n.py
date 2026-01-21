"""Tests for gui/i18n.py module."""

import pytest


class TestLanguageState:
    """Tests for language state management."""

    def test_default_language_is_english(self):
        """Default language should be English."""
        from gui import i18n

        # Reset to default
        i18n._current_language = "en"
        assert i18n.get_language() == "en"

    def test_set_language_to_chinese(self):
        """Can set language to Chinese."""
        from gui import i18n

        i18n.set_language("zh")
        assert i18n.get_language() == "zh"

        # Reset
        i18n.set_language("en")

    def test_set_language_to_english(self):
        """Can set language to English."""
        from gui import i18n

        i18n.set_language("zh")
        i18n.set_language("en")
        assert i18n.get_language() == "en"

    def test_set_invalid_language_ignored(self):
        """Setting invalid language code is ignored."""
        from gui import i18n

        i18n.set_language("en")
        i18n.set_language("invalid")
        assert i18n.get_language() == "en"  # Still English

    def test_set_empty_language_ignored(self):
        """Setting empty language code is ignored."""
        from gui import i18n

        i18n.set_language("en")
        i18n.set_language("")
        assert i18n.get_language() == "en"


class TestGetText:
    """Tests for get_text function."""

    def test_get_text_english(self):
        """get_text returns English text when language is English."""
        from gui import i18n

        i18n.set_language("en")
        assert i18n.get_text("title") == "🚀 AI Studio Proxy API"

    def test_get_text_chinese(self):
        """get_text returns Chinese text when language is Chinese."""
        from gui import i18n

        i18n.set_language("zh")
        result = i18n.get_text("title")
        assert result == "🚀 AI Studio 代理 API"

        # Reset
        i18n.set_language("en")

    def test_get_text_with_format_kwargs(self):
        """get_text supports format placeholders."""
        from gui import i18n

        i18n.set_language("en")
        result = i18n.get_text("log_accounts_loaded", count=5)
        assert "5" in result
        assert "account" in result.lower()

    def test_get_text_unknown_key_returns_placeholder(self):
        """Unknown keys return <key> placeholder."""
        from gui import i18n

        i18n.set_language("en")
        result = i18n.get_text("nonexistent_key_12345")
        assert result == "<nonexistent_key_12345>"

    def test_get_text_fallback_to_english(self):
        """If Chinese translation missing, falls back to English."""
        from gui import i18n

        # All keys should have both translations, but test fallback logic
        i18n.set_language("zh")
        # Access a known key
        result = i18n.get_text("btn_start")
        assert result  # Should not be empty

        i18n.set_language("en")


class TestTranslationsCompleteness:
    """Tests for translation completeness."""

    def test_all_keys_have_english(self):
        """All translation keys should have English text."""
        from gui.i18n import TRANSLATIONS

        for key, translations in TRANSLATIONS.items():
            assert "en" in translations, f"Missing English translation for: {key}"

    def test_all_keys_have_chinese(self):
        """All translation keys should have Chinese text."""
        from gui.i18n import TRANSLATIONS

        for key, translations in TRANSLATIONS.items():
            assert "zh" in translations, f"Missing Chinese translation for: {key}"

    def test_no_empty_translations(self):
        """No translation should be empty."""
        from gui.i18n import TRANSLATIONS

        for key, translations in TRANSLATIONS.items():
            for lang, text in translations.items():
                assert text, f"Empty translation for {key} in {lang}"

    def test_format_placeholders_consistent(self):
        """Format placeholders should match between languages."""
        from gui.i18n import TRANSLATIONS
        import re

        placeholder_pattern = re.compile(r"\{(\w+)\}")

        for key, translations in TRANSLATIONS.items():
            en_placeholders = set(
                placeholder_pattern.findall(translations.get("en", ""))
            )
            zh_placeholders = set(
                placeholder_pattern.findall(translations.get("zh", ""))
            )

            assert en_placeholders == zh_placeholders, (
                f"Placeholder mismatch for {key}: EN={en_placeholders}, ZH={zh_placeholders}"
            )


class TestTranslationCategories:
    """Tests for translation category coverage."""

    def test_has_status_messages(self):
        """Should have status message translations."""
        from gui.i18n import TRANSLATIONS

        status_keys = [
            "status_ready",
            "status_running",
            "status_stopping",
            "status_stopped",
        ]
        for key in status_keys:
            assert key in TRANSLATIONS

    def test_has_tab_labels(self):
        """Should have tab label translations."""
        from gui.i18n import TRANSLATIONS

        tab_keys = ["tab_control", "tab_accounts", "tab_settings", "tab_logs"]
        for key in tab_keys:
            assert key in TRANSLATIONS

    def test_has_button_labels(self):
        """Should have button label translations."""
        from gui.i18n import TRANSLATIONS

        btn_keys = ["btn_start", "btn_stop", "btn_test", "btn_copy"]
        for key in btn_keys:
            assert key in TRANSLATIONS

    def test_has_dialog_messages(self):
        """Should have dialog message translations."""
        from gui.i18n import TRANSLATIONS

        dialog_keys = ["confirm_title", "warning_title", "error_title", "success_title"]
        for key in dialog_keys:
            assert key in TRANSLATIONS

    def test_has_tooltips(self):
        """Should have tooltip translations."""
        from gui.i18n import TRANSLATIONS

        tooltip_keys = [k for k in TRANSLATIONS.keys() if k.startswith("tooltip_")]
        assert len(tooltip_keys) >= 5, "Should have multiple tooltips"

    def test_has_menu_items(self):
        """Should have menu item translations."""
        from gui.i18n import TRANSLATIONS

        menu_keys = ["menu_file", "menu_exit", "menu_help", "menu_about"]
        for key in menu_keys:
            assert key in TRANSLATIONS
