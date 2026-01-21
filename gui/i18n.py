"""
GUI Launcher Internationalization (i18n)

Contains all translations for English and Chinese.
"""

from typing import Dict, Any

# Current language setting (module-level state)
_current_language = "en"


def get_language() -> str:
    """Get current language code."""
    return _current_language


def set_language(lang_code: str) -> None:
    """Set current language code."""
    global _current_language
    if lang_code in ("en", "zh"):
        _current_language = lang_code


def get_text(key: str, **kwargs) -> str:
    """Get translated text for the given key."""
    try:
        text = TRANSLATIONS[key][_current_language]
        if kwargs:
            return text.format(**kwargs)
        return text
    except KeyError:
        # Fallback to English
        try:
            text = TRANSLATIONS[key]["en"]
            if kwargs:
                return text.format(**kwargs)
            return text
        except KeyError:
            return f"<{key}>"


# =============================================================================
# All Translations
# =============================================================================
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # Window title
    "title": {"en": "🚀 AI Studio Proxy API", "zh": "🚀 AI Studio 代理 API"},
    # Status messages
    "status_ready": {"en": "⚪ Ready", "zh": "⚪ 就绪"},
    "status_running": {"en": "🟢 Running", "zh": "🟢 运行中"},
    "status_stopping": {"en": "🟡 Stopping...", "zh": "🟡 停止中..."},
    "status_stopped": {"en": "⚪ Stopped", "zh": "⚪ 已停止"},
    "status_error": {"en": "🔴 Error", "zh": "🔴 错误"},
    # Tabs
    "tab_control": {"en": "🎮 Control", "zh": "🎮 控制"},
    "tab_accounts": {"en": "👤 Accounts", "zh": "👤 账户"},
    "tab_settings": {"en": "⚙️ Settings", "zh": "⚙️ 设置"},
    "tab_logs": {"en": "📋 Logs", "zh": "📋 日志"},
    # Control tab
    "quick_start": {"en": "⚡ Quick Start", "zh": "⚡ 快速启动"},
    "account_label": {"en": "Account:", "zh": "账户:"},
    "mode_label": {"en": "Mode:", "zh": "模式:"},
    "mode_headless": {"en": "Headless", "zh": "无头模式"},
    "mode_visible": {"en": "Visible", "zh": "有头模式"},
    "btn_start": {"en": "▶️ START", "zh": "▶️ 启动"},
    "btn_stop": {"en": "⏹️ STOP", "zh": "⏹️ 停止"},
    "api_info": {"en": "🌐 API Info", "zh": "🌐 API 信息"},
    "btn_test": {"en": "🔍 Test", "zh": "🔍 测试"},
    "btn_open_browser": {"en": "🌐 Open in Browser", "zh": "🌐 在浏览器中打开"},
    "status_card": {"en": "📊 Status", "zh": "📊 状态"},
    "service_stopped": {"en": "Service is stopped", "zh": "服务已停止"},
    "service_started": {"en": "Service started", "zh": "服务已启动"},
    "pid_label": {"en": "PID:", "zh": "进程ID:"},
    # Account tab
    "saved_accounts": {"en": "📋 Saved Accounts", "zh": "📋 已保存账户"},
    "btn_add_account": {"en": "➕ Add New Account", "zh": "➕ 添加新账户"},
    "btn_delete_account": {"en": "🗑️ Delete Selected", "zh": "🗑️ 删除选中"},
    "btn_refresh": {"en": "🔄 Refresh", "zh": "🔄 刷新"},
    "account_details": {"en": "ℹ️ Account Details", "zh": "ℹ️ 账户详情"},
    "select_account_hint": {
        "en": "Select an account to see details",
        "zh": "选择账户查看详情",
    },
    "file_label": {"en": "📁 File:", "zh": "📁 文件:"},
    "last_modified": {"en": "📅 Last modified:", "zh": "📅 最后修改:"},
    "size_label": {"en": "📊 Size:", "zh": "📊 大小:"},
    # Settings tab
    "port_settings": {"en": "🔌 Port Settings", "zh": "🔌 端口设置"},
    "fastapi_port": {"en": "FastAPI Port:", "zh": "FastAPI 端口:"},
    "stream_port": {"en": "Stream Port:", "zh": "流代理端口:"},
    "proxy_settings": {"en": "🌍 Proxy Settings", "zh": "🌍 代理设置"},
    "use_proxy": {"en": "Use Proxy", "zh": "使用代理"},
    "proxy_address": {"en": "Address:", "zh": "地址:"},
    "proxy_example": {
        "en": "Example: http://127.0.0.1:7890",
        "zh": "示例: http://127.0.0.1:7890",
    },
    "language_settings": {"en": "🌐 Language / 语言", "zh": "🌐 Language / 语言"},
    "btn_save_settings": {"en": "💾 Save Settings", "zh": "💾 保存设置"},
    "btn_reset_default": {"en": "🔄 Reset to Default", "zh": "🔄 恢复默认"},
    # Logs tab
    "btn_clear_logs": {"en": "🗑️ Clear", "zh": "🗑️ 清空"},
    "btn_save_logs": {"en": "💾 Save to File", "zh": "💾 保存到文件"},
    "btn_open_log_folder": {"en": "📂 Open Log File", "zh": "📂 打开日志文件"},
    # Dialog messages
    "new_account_title": {"en": "New Account", "zh": "新建账户"},
    "new_account_prompt": {
        "en": "Enter a name for the account\n(e.g.: my_gmail_account):",
        "zh": "请输入账户名称\n(例如: my_gmail_account):",
    },
    "invalid_filename": {
        "en": "Only letters, numbers, - and _ are allowed!",
        "zh": "只允许使用字母、数字、- 和 _！",
    },
    "confirm_delete": {
        "en": "Are you sure you want to delete '{name}'?",
        "zh": "确定要删除 '{name}' 吗？",
    },
    "confirm_title": {"en": "Confirm", "zh": "确认"},
    "warning_title": {"en": "Warning", "zh": "警告"},
    "error_title": {"en": "Error", "zh": "错误"},
    "success_title": {"en": "Success", "zh": "成功"},
    "select_account_warning": {
        "en": "Please select an account to delete",
        "zh": "请选择要删除的账户",
    },
    "select_account_error": {
        "en": "Please select an account!",
        "zh": "请选择一个账户！",
    },
    "service_already_running": {
        "en": "Service is already running!",
        "zh": "服务已在运行中！",
    },
    "api_running": {"en": "API is running! ✅", "zh": "API 运行正常！ ✅"},
    "api_not_responding": {
        "en": "Could not connect to API.\nIs the service running?",
        "zh": "无法连接到 API。\n服务是否在运行？",
    },
    "settings_saved": {"en": "Settings saved!", "zh": "设置已保存！"},
    "reset_confirm": {
        "en": "All settings will be reset to default. Continue?",
        "zh": "所有设置将恢复为默认值。继续吗？",
    },
    "exit_confirm": {
        "en": "Service is running. Stop and exit?",
        "zh": "服务正在运行。停止并退出吗？",
    },
    "logs_saved": {"en": "Logs saved:", "zh": "日志已保存:"},
    "logs_save_error": {"en": "Logs could not be saved:", "zh": "无法保存日志:"},
    "folder_open_error": {"en": "Folder could not be opened:", "zh": "无法打开文件夹:"},
    "account_delete_error": {
        "en": "Account could not be deleted:",
        "zh": "无法删除账户:",
    },
    "start_error": {"en": "Could not start:", "zh": "无法启动:"},
    # Log messages
    "log_ready": {
        "en": "🚀 AI Studio Proxy Launcher ready",
        "zh": "🚀 AI Studio 代理启动器就绪",
    },
    "log_accounts_loaded": {
        "en": "✅ {count} account(s) loaded",
        "zh": "✅ 已加载 {count} 个账户",
    },
    "log_no_accounts": {
        "en": "⚠️ No saved accounts found",
        "zh": "⚠️ 未找到已保存的账户",
    },
    "log_adding_account": {
        "en": "🔐 Adding new account: {name}",
        "zh": "🔐 正在添加新账户: {name}",
    },
    "log_browser_login": {
        "en": "📌 Browser will open, log in to your Google account",
        "zh": "📌 浏览器将打开，请登录您的 Google 账户",
    },
    "log_auto_save": {
        "en": "📌 After logging in, account will be saved automatically",
        "zh": "📌 登录后，账户将自动保存",
    },
    "log_account_deleted": {
        "en": "🗑️ Account deleted: {name}",
        "zh": "🗑️ 账户已删除: {name}",
    },
    "log_testing_api": {"en": "🔍 Testing API: {url}", "zh": "🔍 正在测试 API: {url}"},
    "log_api_running": {"en": "✅ API is running!", "zh": "✅ API 运行正常！"},
    "log_api_status": {
        "en": "⚠️ API responded but status code: {code}",
        "zh": "⚠️ API 响应但状态码: {code}",
    },
    "log_api_error": {
        "en": "❌ Could not connect to API. Service may not be running.",
        "zh": "❌ 无法连接到 API。服务可能未运行。",
    },
    "log_api_test_error": {
        "en": "❌ API test error: {error}",
        "zh": "❌ API 测试错误: {error}",
    },
    "log_settings_saved": {"en": "💾 Settings saved", "zh": "💾 设置已保存"},
    "log_settings_reset": {
        "en": "🔄 Settings reset to default",
        "zh": "🔄 设置已恢复默认",
    },
    "log_checking_ports": {"en": "🔍 Checking ports...", "zh": "🔍 正在检查端口..."},
    "log_port_in_use": {
        "en": "🔍 Port {port} is in use, cleaning...",
        "zh": "🔍 端口 {port} 被占用，正在清理...",
    },
    "log_pid_terminated": {
        "en": "   ✅ PID {pid} terminated",
        "zh": "   ✅ PID {pid} 已终止",
    },
    "log_pid_error": {
        "en": "   ❌ PID {pid}: {error}",
        "zh": "   ❌ PID {pid}: {error}",
    },
    "log_port_still_in_use": {
        "en": "   ❌ Port {port} is still in use!",
        "zh": "   ❌ 端口 {port} 仍被占用！",
    },
    "log_starting": {
        "en": "🚀 Starting: {mode} mode",
        "zh": "🚀 正在启动: {mode} 模式",
    },
    "log_service_started": {
        "en": "✅ Service started (PID: {pid})",
        "zh": "✅ 服务已启动 (PID: {pid})",
    },
    "log_stopping": {"en": "🛑 Stopping...", "zh": "🛑 正在停止..."},
    "log_force_closing": {"en": "⚠️ Force closing...", "zh": "⚠️ 正在强制关闭..."},
    "log_stopped": {"en": "✅ Stopped", "zh": "✅ 已停止"},
    "log_stop_error": {"en": "❌ Stop error: {error}", "zh": "❌ 停止错误: {error}"},
    "log_service_ended": {"en": "✅ Service ended normally", "zh": "✅ 服务正常结束"},
    "log_service_error": {
        "en": "⚠️ Service stopped with error: {code}",
        "zh": "⚠️ 服务异常停止，错误码: {code}",
    },
    "log_minimized": {
        "en": "📌 Minimized to system tray",
        "zh": "📌 已最小化到系统托盘",
    },
    "log_accounts_refreshed": {
        "en": "🔄 Account list refreshed",
        "zh": "🔄 账户列表已刷新",
    },
    "log_language_changed": {
        "en": "🌐 Language changed to English",
        "zh": "🌐 语言已切换为中文",
    },
    "log_config_load_error": {
        "en": "⚠️ Configuration could not be loaded: {error}",
        "zh": "⚠️ 无法加载配置: {error}",
    },
    "log_config_save_error": {
        "en": "⚠️ Configuration could not be saved: {error}",
        "zh": "⚠️ 无法保存配置: {error}",
    },
    "log_logs_saved": {"en": "✅ Logs saved: {name}", "zh": "✅ 日志已保存: {name}"},
    "log_port_pid_error": {
        "en": "⚠️ Could not find port PID: {error}",
        "zh": "⚠️ 无法查找端口 PID: {error}",
    },
    "log_user_cancelled": {"en": "❌ User cancelled", "zh": "❌ 用户取消"},
    "log_port_clean_warning": {
        "en": "Some ports could not be cleaned. Continue?",
        "zh": "部分端口无法清理。是否继续？",
    },
    # API status
    "api_active": {
        "en": "✅ API is active and responding",
        "zh": "✅ API 活跃且响应正常",
    },
    "api_not_active": {"en": "❌ API is not responding", "zh": "❌ API 无响应"},
    # Menu bar
    "menu_file": {"en": "File", "zh": "文件"},
    "menu_start_service": {"en": "Start Service", "zh": "启动服务"},
    "menu_stop_service": {"en": "Stop Service", "zh": "停止服务"},
    "menu_exit": {"en": "Exit", "zh": "退出"},
    "menu_help": {"en": "Help", "zh": "帮助"},
    "menu_about": {"en": "About", "zh": "关于"},
    "menu_documentation": {"en": "Documentation", "zh": "文档"},
    "menu_github": {"en": "GitHub Repository", "zh": "GitHub 仓库"},
    # About dialog
    "about_title": {"en": "About AI Studio Proxy", "zh": "关于 AI Studio 代理"},
    "about_version": {"en": "Version:", "zh": "版本:"},
    "about_description": {
        "en": "A proxy server that converts Google AI Studio's web interface into an OpenAI-compatible API.",
        "zh": "将 Google AI Studio 网页界面转换为兼容 OpenAI API 的代理服务器。",
    },
    "about_credits": {"en": "Credits:", "zh": "致谢:"},
    # Tooltips
    "tooltip_account": {
        "en": "Select the Google account to use for authentication",
        "zh": "选择用于身份验证的 Google 账户",
    },
    "tooltip_headless": {
        "en": "Run browser in background (no visible window)",
        "zh": "在后台运行浏览器（无可见窗口）",
    },
    "tooltip_visible": {
        "en": "Show browser window (useful for debugging)",
        "zh": "显示浏览器窗口（用于调试）",
    },
    "tooltip_start": {
        "en": "Start the proxy service (Ctrl+S)",
        "zh": "启动代理服务 (Ctrl+S)",
    },
    "tooltip_stop": {
        "en": "Stop the running service (Ctrl+X)",
        "zh": "停止正在运行的服务 (Ctrl+X)",
    },
    "tooltip_test_api": {"en": "Test if API is responding", "zh": "测试 API 是否响应"},
    "tooltip_copy_url": {
        "en": "Copy API URL to clipboard",
        "zh": "复制 API 地址到剪贴板",
    },
    "tooltip_add_account": {
        "en": "Open browser to log in with a new Google account",
        "zh": "打开浏览器以使用新的 Google 账户登录",
    },
    "tooltip_delete_account": {
        "en": "Delete the selected account",
        "zh": "删除选中的账户",
    },
    "tooltip_fastapi_port": {
        "en": "Port for the OpenAI-compatible API (default: 2048)",
        "zh": "OpenAI 兼容 API 的端口（默认：2048）",
    },
    "tooltip_stream_port": {
        "en": "Port for streaming proxy (default: 3120)",
        "zh": "流代理端口（默认：3120）",
    },
    "tooltip_proxy": {
        "en": "HTTP proxy for accessing Google (e.g., http://127.0.0.1:7890)",
        "zh": "访问 Google 的 HTTP 代理（例如：http://127.0.0.1:7890）",
    },
    # Status bar
    "statusbar_ready": {"en": "Ready", "zh": "就绪"},
    "statusbar_running": {"en": "Running", "zh": "运行中"},
    "statusbar_uptime": {"en": "Uptime:", "zh": "运行时间:"},
    "statusbar_port": {"en": "Port:", "zh": "端口:"},
    # Copy
    "copied_to_clipboard": {"en": "Copied to clipboard!", "zh": "已复制到剪贴板！"},
    "btn_copy": {"en": "📋 Copy", "zh": "📋 复制"},
    # Empty states
    "no_accounts_title": {"en": "No Accounts Found", "zh": "未找到账户"},
    "no_accounts_hint": {
        "en": "Click '➕ Add New Account' to get started",
        "zh": "点击 '➕ 添加新账户' 开始",
    },
    # Validation
    "invalid_port": {
        "en": "Invalid port number. Must be between 1 and 65535.",
        "zh": "无效的端口号。必须在 1 到 65535 之间。",
    },
    "port_conflict": {
        "en": "FastAPI and Stream ports cannot be the same.",
        "zh": "FastAPI 端口和流代理端口不能相同。",
    },
    # Theme settings
    "theme_settings": {"en": "🎨 Appearance", "zh": "🎨 外观"},
    "theme_mode": {"en": "Theme Mode:", "zh": "主题模式:"},
    "theme_dark": {"en": "🌙 Dark", "zh": "🌙 深色"},
    "theme_light": {"en": "☀️ Light", "zh": "☀️ 浅色"},
    "theme_system": {"en": "💻 System", "zh": "💻 跟随系统"},
    "log_theme_changed": {
        "en": "🎨 Theme changed to {mode}",
        "zh": "🎨 主题已切换为 {mode}",
    },
    "tooltip_theme": {
        "en": "Choose your preferred appearance mode",
        "zh": "选择您偏好的外观模式",
    },
    # =========================================================================
    # Advanced Settings
    # =========================================================================
    "advanced_settings": {"en": "🔧 Advanced Settings", "zh": "🔧 高级设置"},
    "advanced_settings_hint": {
        "en": "Configure .env file settings (click to expand/collapse)",
        "zh": "配置 .env 文件设置（点击展开/折叠）",
    },
    "show_advanced": {"en": "▶ Show Advanced Settings", "zh": "▶ 显示高级设置"},
    "hide_advanced": {"en": "▼ Hide Advanced Settings", "zh": "▼ 隐藏高级设置"},
    # Category names
    "cat_server": {"en": "🖥️ Server Configuration", "zh": "🖥️ 服务器配置"},
    "cat_logging": {"en": "📝 Logging & Debugging", "zh": "📝 日志与调试"},
    "cat_auth": {"en": "🔐 Authentication", "zh": "🔐 认证设置"},
    "cat_cookie": {"en": "🍪 Cookie Refresh", "zh": "🍪 Cookie 刷新"},
    "cat_browser": {"en": "🌐 Browser & Model", "zh": "🌐 浏览器与模型"},
    "cat_api": {"en": "⚡ API Defaults", "zh": "⚡ API 默认参数"},
    "cat_function_calling": {"en": "🔧 Function Calling", "zh": "🔧 函数调用"},
    "cat_timeouts": {"en": "⏱️ Timeouts", "zh": "⏱️ 超时设置"},
    "cat_misc": {"en": "📦 Miscellaneous", "zh": "📦 其他设置"},
    # Action buttons
    "btn_apply_env": {"en": "💾 Apply Changes", "zh": "💾 应用更改"},
    "btn_reload_env": {"en": "🔄 Reload from File", "zh": "🔄 从文件重载"},
    "btn_reset_env": {"en": "⚙️ Reset to Defaults", "zh": "⚙️ 恢复默认值"},
    "btn_hot_reload": {"en": "🔥 Hot Reload", "zh": "🔥 热重载"},
    # Status messages
    "env_saved": {
        "en": "Environment settings saved to .env",
        "zh": "环境设置已保存到 .env",
    },
    "env_save_error": {"en": "Failed to save .env file", "zh": "保存 .env 文件失败"},
    "env_reloaded": {
        "en": "Settings reloaded from .env file",
        "zh": "设置已从 .env 文件重新加载",
    },
    "env_reset_confirm": {
        "en": "Reset all advanced settings to defaults? This cannot be undone.",
        "zh": "将所有高级设置恢复为默认值？此操作不可撤销。",
    },
    "env_reset_done": {"en": "Settings reset to defaults", "zh": "设置已恢复默认"},
    "env_unsaved_changes": {
        "en": "You have unsaved changes. Save before continuing?",
        "zh": "您有未保存的更改。是否在继续前保存？",
    },
    "env_hot_reload_success": {
        "en": "Settings applied via hot reload",
        "zh": "设置已通过热重载应用",
    },
    "env_hot_reload_warning": {
        "en": "Proxy is running. Some settings require restart to take effect.",
        "zh": "代理正在运行。部分设置需要重启才能生效。",
    },
    "env_hot_reload_confirm": {
        "en": "Apply settings to running proxy? Some changes may require restart.",
        "zh": "将设置应用到正在运行的代理？部分更改可能需要重启。",
    },
    "env_modified_indicator": {"en": "(modified)", "zh": "（已修改）"},
    "env_file_not_found": {
        "en": ".env file not found. Created from template.",
        "zh": "未找到 .env 文件。已从模板创建。",
    },
    # Tooltips for settings
    "tooltip_env_port": {
        "en": "Main API server port (default: 2048)",
        "zh": "主 API 服务器端口（默认：2048）",
    },
    "tooltip_env_stream_port": {
        "en": "Streaming proxy port. Set to 0 to disable (default: 3120)",
        "zh": "流代理端口。设置为 0 禁用（默认：3120）",
    },
    "tooltip_env_log_level": {
        "en": "Server log verbosity level",
        "zh": "服务器日志详细程度",
    },
    "tooltip_env_temperature": {
        "en": "Default sampling temperature (0.0-2.0)",
        "zh": "默认采样温度（0.0-2.0）",
    },
    "tooltip_env_max_tokens": {
        "en": "Maximum output tokens per request",
        "zh": "每次请求的最大输出令牌数",
    },
    "tooltip_env_auto_rotate": {
        "en": "Automatically switch auth profile when quota exceeded",
        "zh": "配额超限时自动切换认证配置文件",
    },
    "tooltip_env_quota_soft": {
        "en": "Token count that triggers rotation pending state",
        "zh": "触发待轮换状态的令牌计数",
    },
    "tooltip_env_quota_hard": {
        "en": "Token count that triggers immediate rotation",
        "zh": "触发立即轮换的令牌计数",
    },
    "tooltip_env_fc_mode": {
        "en": "Function calling mode: auto (recommended), native, or emulated",
        "zh": "函数调用模式：auto（推荐）、native 或 emulated",
    },
    "tooltip_env_hot_reload": {
        "en": "Apply settings immediately without restart (some settings require restart)",
        "zh": "立即应用设置无需重启（部分设置需要重启）",
    },
    # Log messages for advanced settings
    "log_env_loaded": {
        "en": "📁 Advanced settings loaded from .env",
        "zh": "📁 高级设置已从 .env 加载",
    },
    "log_env_saved": {
        "en": "💾 Advanced settings saved to .env",
        "zh": "💾 高级设置已保存到 .env",
    },
    "log_env_hot_reload": {
        "en": "🔥 Hot reload applied: {count} setting(s) updated",
        "zh": "🔥 热重载已应用：{count} 个设置已更新",
    },
    "log_env_reset": {
        "en": "⚙️ Advanced settings reset to defaults",
        "zh": "⚙️ 高级设置已恢复默认",
    },
}
