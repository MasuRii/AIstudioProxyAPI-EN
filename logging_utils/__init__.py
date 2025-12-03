# 日志设置功能
# Grid logging system v2.0
from .grid_logger import (
    # Source mapping
    SOURCE_MAP,
    # Classes
    AbortErrorFilter,
    BrowserNoiseFilter,
    BurstBuffer,
    Colors,
    Columns,
    GridFormatter,
    PlainGridFormatter,
    ProgressLine,
    SemanticHighlighter,
    TreeBuilder,
    # Utility functions
    flush_burst_buffer,
    format_object,
    get_request_id,
    get_source,
    # Context managers
    log_context,
    log_object,
    normalize_source,
    request_context,
    # Context variables
    request_id_var,
    set_request_id,
    set_source,
    setup_grid_logging,
    source_var,
    tree_depth_var,
    tree_stack_var,
)
from .setup import restore_original_streams, setup_server_logging

__all__ = [
    # Legacy setup
    "setup_server_logging",
    "restore_original_streams",
    # Grid logger
    "setup_grid_logging",
    "GridFormatter",
    "PlainGridFormatter",
    "AbortErrorFilter",
    "BrowserNoiseFilter",
    "Colors",
    "Columns",
    "TreeBuilder",
    "SemanticHighlighter",
    "ProgressLine",
    "BurstBuffer",
    # Context managers
    "log_context",
    "request_context",
    # Context variables
    "request_id_var",
    "source_var",
    "tree_depth_var",
    "tree_stack_var",
    # Source mapping
    "SOURCE_MAP",
    "normalize_source",
    # Utility functions
    "set_source",
    "set_request_id",
    "get_source",
    "get_request_id",
    "format_object",
    "log_object",
    "flush_burst_buffer",
]
