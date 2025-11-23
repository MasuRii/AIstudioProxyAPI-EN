"""
超时和时间配置模块
包含所有超时时间、轮询间隔等时间相关配置
"""

import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# --- 响应等待配置 ---
RESPONSE_COMPLETION_TIMEOUT = int(os.environ.get('RESPONSE_COMPLETION_TIMEOUT', '300000'))  # 5 minutes total timeout (in ms)
INITIAL_WAIT_MS_BEFORE_POLLING = int(os.environ.get('INITIAL_WAIT_MS_BEFORE_POLLING', '500'))  # ms, initial wait before polling for response completion

# --- 轮询间隔配置 ---
POLLING_INTERVAL = int(os.environ.get('POLLING_INTERVAL', '300'))  # ms
POLLING_INTERVAL_STREAM = int(os.environ.get('POLLING_INTERVAL_STREAM', '180'))  # ms

# --- 静默超时配置 ---
SILENCE_TIMEOUT_MS = int(os.environ.get('SILENCE_TIMEOUT_MS', '60000'))  # ms

# --- 页面操作超时配置 ---
POST_SPINNER_CHECK_DELAY_MS = int(os.environ.get('POST_SPINNER_CHECK_DELAY_MS', '500'))
FINAL_STATE_CHECK_TIMEOUT_MS = int(os.environ.get('FINAL_STATE_CHECK_TIMEOUT_MS', '1500'))
POST_COMPLETION_BUFFER = int(os.environ.get('POST_COMPLETION_BUFFER', '700'))

# --- 清理聊天相关超时 ---
CLEAR_CHAT_VERIFY_TIMEOUT_MS = int(os.environ.get('CLEAR_CHAT_VERIFY_TIMEOUT_MS', '5000'))
CLEAR_CHAT_VERIFY_INTERVAL_MS = int(os.environ.get('CLEAR_CHAT_VERIFY_INTERVAL_MS', '2000'))

# --- 点击和剪贴板操作超时 ---
CLICK_TIMEOUT_MS = int(os.environ.get('CLICK_TIMEOUT_MS', '3000'))
CLIPBOARD_READ_TIMEOUT_MS = int(os.environ.get('CLIPBOARD_READ_TIMEOUT_MS', '3000'))

# --- 元素等待超时 ---
WAIT_FOR_ELEMENT_TIMEOUT_MS = int(os.environ.get('WAIT_FOR_ELEMENT_TIMEOUT_MS', '10000'))  # Timeout for waiting for elements like overlays

# --- 自适应冷却时间配置 (Adaptive Cooldowns) ---
# Rate Limit (429) - 较短的冷却时间 (默认 5 分钟)
RATE_LIMIT_COOLDOWN_SECONDS = int(os.environ.get('RATE_LIMIT_COOLDOWN_SECONDS', '300'))
# Quota Exceeded (Resource Exhausted) - 较长的冷却时间 (默认 4 小时)
QUOTA_EXCEEDED_COOLDOWN_SECONDS = int(os.environ.get('QUOTA_EXCEEDED_COOLDOWN_SECONDS', '14400'))

# --- 流相关配置 ---
PSEUDO_STREAM_DELAY = float(os.environ.get('PSEUDO_STREAM_DELAY', '0.01'))