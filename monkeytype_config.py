"""MonkeyType configuration for AIStudioProxyAPI.

This config:
- Filters to only trace project modules (exclude tests, external libs)
- Enables TypedDict generation for config dicts
- Applies type rewriters to clean up messy unions
- Increases query limit for comprehensive coverage
"""

from monkeytype.config import DefaultConfig
from monkeytype.typing import (
    ChainedRewriter,
    RemoveEmptyContainers,
    RewriteConfigDict,
    RewriteLargeUnion,
)


class AIStudioProxyConfig(DefaultConfig):
    """Custom MonkeyType configuration for this project."""

    def code_filter(self):
        """Only trace project modules, exclude tests and external libraries."""

        def should_trace(code):
            # Normalize Windows path separators
            filename = code.co_filename.replace("\\", "/")

            # Project modules to trace
            project_modules = [
                "api_utils",
                "browser_utils",
                "stream",
                "config",
                "models",
                "launcher",
                "logging_utils",
            ]

            # Check if file is in any project module
            for module in project_modules:
                if f"/{module}/" in filename or filename.endswith(f"/{module}.py"):
                    # Exclude test files
                    if "/tests/" not in filename and "/test_" not in filename:
                        return True

            return False

        return should_trace

    def type_rewriter(self):
        """Clean up generated types with chained rewriters."""
        return ChainedRewriter(
            [
                RemoveEmptyContainers(),  # Union[List[Any], List[int]] -> List[int]
                RewriteConfigDict(),  # Union[Dict[K,V1], Dict[K,V2]] -> Dict[K, Union[V1,V2]]
                RewriteLargeUnion(
                    max_union_len=3
                ),  # Large unions -> Any (strict: max 3 elements)
            ]
        )

    def max_typed_dict_size(self) -> int:
        """Enable TypedDict generation for dictionaries.

        Since 19.11.2, TypedDict generation is disabled by default.
        This enables it for dicts with up to 50 keys, which is critical
        for config.settings and similar modules.
        """
        return 50

    def query_limit(self) -> int:
        """Increase query limit for comprehensive type inference.

        Default is 2000. We increase to 5000 to capture more traces
        and improve type accuracy, especially for polymorphic functions.
        """
        return 5000


# MonkeyType will automatically find and use this CONFIG instance
CONFIG = AIStudioProxyConfig()
