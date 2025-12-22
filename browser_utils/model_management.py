"""
browser_utils/model_management.py
---------------------------------
Shim module for backward compatibility.
Refactored logic is now located in browser_utils.models.*
"""

from browser_utils.models.startup import (
    _handle_initial_model_state_and_storage,
    _set_model_from_page_display,
)
from browser_utils.models.switcher import (
    load_excluded_models,
    switch_ai_studio_model,
)
from browser_utils.models.ui_state import (
    _force_ui_state_settings,
    _force_ui_state_with_retry,
    _verify_and_apply_ui_state,
    _verify_ui_state_settings,
)

__all__ = [
    "_verify_ui_state_settings",
    "_force_ui_state_settings",
    "_force_ui_state_with_retry",
    "_verify_and_apply_ui_state",
    "switch_ai_studio_model",
    "load_excluded_models",
    "_handle_initial_model_state_and_storage",
    "_set_model_from_page_display",
]
