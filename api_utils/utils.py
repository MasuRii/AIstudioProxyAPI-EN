"""
API工具函数模块
包含SSE生成、流处理、token统计和请求验证等工具函数
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, AsyncGenerator, Tuple, Union
from models import Message
import re
import base64
import requests  # retained for potential outbound helpers; remove if unused later
import os
import hashlib
from urllib.parse import urlparse, unquote
from .tools_registry import execute_tool_call, register_runtime_tools
from .sse import (
    generate_sse_chunk,
    generate_sse_stop_chunk,
    generate_sse_error_chunk,
)
from .utils_ext import (
    use_stream_response,
    clear_stream_queue,
    use_helper_get_response,
    validate_chat_request,
    _extension_for_mime,
    extract_data_url_to_local,
    save_blob_to_local,
    estimate_tokens,
    calculate_usage_stats,
)


# --- SSE生成函数 ---
## SSE helpers moved to api_utils.sse and re-exported here


## stream helpers moved to utils_ext.stream


# --- Helper response generator ---
## helper generator moved to utils_ext.helper


# --- 请求验证函数 ---
## validation moved to utils_ext.validation


## files helpers moved to utils_ext.files


# --- 提示准备函数 ---
def prepare_combined_prompt(messages: List[Message], req_id: str, tools: Optional[List[Dict[str, Any]]] = None, tool_choice: Optional[Union[str, Dict[str, Any]]] = None) -> Tuple[str, List[str]]:
    """准备组合提示"""
    from server import logger
    
    logger.info(f"[{req_id}] (准备提示) 正在从 {len(messages)} 条消息准备组合提示 (包括历史)。")
    # 不在此处清空 upload_files；由上层在每次请求开始时按需清理，避免历史附件丢失导致“文件不存在”错误。
    
    combined_parts = []
    system_prompt_content: Optional[str] = None
    processed_system_message_indices = set()
    files_list: List[str] = []  # 收集需要上传的本地文件路径（图片、视频、PDF等）

    # 若声明了可用工具，先在提示前注入工具目录，帮助模型知晓可用函数（内部适配，不影响外部协议）
    if isinstance(tools, list) and len(tools) > 0:
        try:
            tool_lines: List[str] = ["可用工具目录:"]
            for t in tools:
                name = None
                params_schema = None
                if isinstance(t, dict):
                    fn = t.get('function') if 'function' in t else t
                    if isinstance(fn, dict):
                        name = fn.get('name') or t.get('name')
                        params_schema = fn.get('parameters')
                    else:
                        name = t.get('name')
                if name:
                    tool_lines.append(f"- 函数: {name}")
                    if params_schema:
                        try:
                            tool_lines.append(f"  参数模式: {json.dumps(params_schema, ensure_ascii=False)}")
                        except Exception:
                            pass
            if tool_choice:
                # 明确要求或提示可调用的函数名
                chosen_name = None
                if isinstance(tool_choice, dict):
                    fn = tool_choice.get('function') if tool_choice else None
                    if isinstance(fn, dict):
                        chosen_name = fn.get('name')
                elif isinstance(tool_choice, str) and tool_choice.lower() not in ('auto', 'none', 'no', 'off', 'required', 'any'):
                    chosen_name = tool_choice
                if chosen_name:
                    tool_lines.append(f"建议优先使用函数: {chosen_name}")
            combined_parts.append("\n".join(tool_lines) + "\n---\n")
        except Exception:
            pass

    # 处理系统消息
    for i, msg in enumerate(messages):
        if msg.role == 'system':
            content = msg.content
            if isinstance(content, str) and content.strip():
                system_prompt_content = content.strip()
                processed_system_message_indices.add(i)
                logger.info(f"[{req_id}] (准备提示) 在索引 {i} 找到并使用系统提示: '{system_prompt_content[:80]}...'")
                system_instr_prefix = "System Command:\n"
                combined_parts.append(f"{system_instr_prefix}{system_prompt_content}")
            else:
                logger.info(f"[{req_id}] (准备提示) 在索引 {i} 忽略非字符串或空的系统消息。")
                processed_system_message_indices.add(i)
            break
    
    role_map_ui = {"user": "用户", "assistant": "助手", "system": "系统", "tool": "工具"}
    turn_separator = "\n---\n"
    
    # 处理其他消息
    for i, msg in enumerate(messages):
        if i in processed_system_message_indices:
            continue
        
        if msg.role == 'system':
            logger.info(f"[{req_id}] (准备提示) 跳过在索引 {i} 的后续系统消息。")
            continue
        
        if combined_parts:
            combined_parts.append(turn_separator)
        
        role = msg.role or 'unknown'
        role_prefix_ui = f"{role_map_ui.get(role, role.capitalize())}:\n"
        current_turn_parts = [role_prefix_ui]
        
        content = msg.content or ''
        content_str = ""
        
        if isinstance(content, str):
            content_str = content.strip()
        elif isinstance(content, list):
            # 处理多模态内容（更健壮地识别各类附件项）
            text_parts = []
            for item in content:
                # 统一获取项类型（可能缺失）
                item_type = None
                if hasattr(item, 'type'):
                    try:
                        item_type = item.type
                    except Exception:
                        item_type = None
                if item_type is None and isinstance(item, dict):
                    item_type = item.get('type')

                if item_type == 'text':
                    # 文本项
                    if hasattr(item, 'text'):
                        text_parts.append(getattr(item, 'text', '') or '')
                    elif isinstance(item, dict):
                        text_parts.append(item.get('text', ''))
                    continue

                # 图片/文件/媒体 URL 项（类型缺失时也尝试识别）
                if item_type in ('image_url', 'file_url', 'media_url', 'input_image') or (
                    isinstance(item, dict) and (
                        'image_url' in item or 'input_image' in item or 'file_url' in item or 'media_url' in item or 'url' in item
                    )
                ):
                    try:
                        url_value = None
                        # Pydantic 对象属性
                        if hasattr(item, 'image_url') and item.image_url:
                            url_value = item.image_url.url
                            try:
                                detail_val = getattr(item.image_url, 'detail', None)
                                if detail_val:
                                    text_parts.append(f"[图像细节: detail={detail_val}]")
                            except Exception:
                                pass
                        elif hasattr(item, 'input_image') and item.input_image:
                            url_value = item.input_image.url
                            try:
                                detail_val = getattr(item.input_image, 'detail', None)
                                if detail_val:
                                    text_parts.append(f"[图像细节: detail={detail_val}]")
                            except Exception:
                                pass
                        elif hasattr(item, 'file_url') and item.file_url:
                            url_value = item.file_url.url
                        elif hasattr(item, 'media_url') and item.media_url:
                            url_value = item.media_url.url
                        elif hasattr(item, 'url') and item.url:
                            url_value = item.url
                        # 字典结构
                        if url_value is None and isinstance(item, dict):
                            if isinstance(item.get('image_url'), dict):
                                url_value = item['image_url'].get('url')
                                detail_val = item['image_url'].get('detail')
                                if detail_val:
                                    text_parts.append(f"[图像细节: detail={detail_val}]")
                            elif isinstance(item.get('image_url'), str):
                                url_value = item.get('image_url')
                            elif isinstance(item.get('input_image'), dict):
                                url_value = item['input_image'].get('url')
                                detail_val = item['input_image'].get('detail')
                                if detail_val:
                                    text_parts.append(f"[图像细节: detail={detail_val}]")
                            elif isinstance(item.get('input_image'), str):
                                url_value = item.get('input_image')
                            elif isinstance(item.get('file_url'), dict):
                                url_value = item['file_url'].get('url')
                            elif isinstance(item.get('file_url'), str):
                                url_value = item.get('file_url')
                            elif isinstance(item.get('media_url'), dict):
                                url_value = item['media_url'].get('url')
                            elif isinstance(item.get('media_url'), str):
                                url_value = item.get('media_url')
                            elif 'url' in item:
                                url_value = item.get('url')
                            elif isinstance(item.get('file'), dict):
                                # 兼容通用 file 字段
                                url_value = item['file'].get('url') or item['file'].get('path')

                        url_value = (url_value or '').strip()
                        if not url_value:
                            continue

                        # 归一化到本地文件列表，并记录日志
                        if url_value.startswith('data:'):
                            file_path = extract_data_url_to_local(url_value, req_id=req_id)
                            if file_path:
                                files_list.append(file_path)
                                logger.info(f"[{req_id}] (准备提示) 已识别并加入 data:URL 附件: {file_path}")
                        elif url_value.startswith('file:'):
                            parsed = urlparse(url_value)
                            local_path = unquote(parsed.path)
                            if os.path.exists(local_path):
                                files_list.append(local_path)
                                logger.info(f"[{req_id}] (准备提示) 已识别并加入本地附件(file://): {local_path}")
                            else:
                                logger.warning(f"[{req_id}] (准备提示) file URL 指向的本地文件不存在: {local_path}")
                        elif os.path.isabs(url_value) and os.path.exists(url_value):
                            files_list.append(url_value)
                            logger.info(f"[{req_id}] (准备提示) 已识别并加入本地附件(绝对路径): {url_value}")
                        else:
                            logger.info(f"[{req_id}] (准备提示) 忽略非本地附件 URL: {url_value}")
                    except Exception as e:
                        logger.warning(f"[{req_id}] (准备提示) 处理附件 URL 时发生错误: {e}")
                    continue

                # 音/视频输入
                if item_type in ('input_audio', 'input_video'):
                    try:
                        inp = None
                        if hasattr(item, 'input_audio') and item.input_audio:
                            inp = item.input_audio
                        elif hasattr(item, 'input_video') and item.input_video:
                            inp = item.input_video
                        elif isinstance(item, dict):
                            inp = item.get('input_audio') or item.get('input_video')

                        if inp:
                            url_value = None
                            data_val = None
                            mime_val = None
                            fmt_val = None
                            if isinstance(inp, dict):
                                url_value = inp.get('url')
                                data_val = inp.get('data')
                                mime_val = inp.get('mime_type')
                                fmt_val = inp.get('format')
                            else:
                                url_value = getattr(inp, 'url', None)
                                data_val = getattr(inp, 'data', None)
                                mime_val = getattr(inp, 'mime_type', None)
                                fmt_val = getattr(inp, 'format', None)

                            if url_value:
                                if url_value.startswith('data:'):
                                    saved = extract_data_url_to_local(url_value, req_id=req_id)
                                    if saved:
                                        files_list.append(saved)
                                        logger.info(f"[{req_id}] (准备提示) 已识别并加入音视频 data:URL 附件: {saved}")
                                elif url_value.startswith('file:'):
                                    parsed = urlparse(url_value)
                                    local_path = unquote(parsed.path)
                                    if os.path.exists(local_path):
                                        files_list.append(local_path)
                                        logger.info(f"[{req_id}] (准备提示) 已识别并加入音视频本地附件(file://): {local_path}")
                                elif os.path.isabs(url_value) and os.path.exists(url_value):
                                    files_list.append(url_value)
                                    logger.info(f"[{req_id}] (准备提示) 已识别并加入音视频本地附件(绝对路径): {url_value}")
                            elif data_val:
                                if isinstance(data_val, str) and data_val.startswith('data:'):
                                    saved = extract_data_url_to_local(data_val, req_id=req_id)
                                    if saved:
                                        files_list.append(saved)
                                        logger.info(f"[{req_id}] (准备提示) 已识别并加入音视频 data:URL 附件: {saved}")
                                else:
                                    # 认为是纯 base64 数据
                                    try:
                                        raw = base64.b64decode(data_val)
                                        saved = save_blob_to_local(raw, mime_val, fmt_val, req_id=req_id)
                                        if saved:
                                            files_list.append(saved)
                                            logger.info(f"[{req_id}] (准备提示) 已识别并加入音视频 base64 附件: {saved}")
                                    except Exception:
                                        pass
                    except Exception as e:
                        logger.warning(f"[{req_id}] (准备提示) 处理音视频输入时出错: {e}")
                    continue

                # 其他未知项：记录而不影响
                logger.warning(f"[{req_id}] (准备提示) 警告: 在索引 {i} 的消息中忽略非文本或未知类型的 content item")
            content_str = "\n".join(text_parts).strip()
        elif isinstance(content, dict):
            # 兼容字典形式的内容，可能包含 'attachments'/'images'/'media'/'files'
            text_parts = []
            attachments_keys = ['attachments', 'images', 'media', 'files']
            for key in attachments_keys:
                items = content.get(key)
                if isinstance(items, list):
                    for it in items:
                        url_value = None
                        if isinstance(it, str):
                            url_value = it
                        elif isinstance(it, dict):
                            url_value = it.get('url') or it.get('path')
                            if not url_value and isinstance(it.get('image_url'), dict):
                                url_value = it['image_url'].get('url')
                            elif not url_value and isinstance(it.get('input_image'), dict):
                                url_value = it['input_image'].get('url')
                        url_value = (url_value or '').strip()
                        if not url_value:
                            continue
                        if url_value.startswith('data:'):
                            fp = extract_data_url_to_local(url_value)
                            if fp:
                                files_list.append(fp)
                                logger.info(f"[{req_id}] (准备提示) 已识别并加入字典附件 data:URL: {fp}")
                        elif url_value.startswith('file:'):
                            parsed = urlparse(url_value)
                            lp = unquote(parsed.path)
                            if os.path.exists(lp):
                                files_list.append(lp)
                                logger.info(f"[{req_id}] (准备提示) 已识别并加入字典附件 file://: {lp}")
                        elif os.path.isabs(url_value) and os.path.exists(url_value):
                            files_list.append(url_value)
                            logger.info(f"[{req_id}] (准备提示) 已识别并加入字典附件绝对路径: {url_value}")
                        else:
                            logger.info(f"[{req_id}] (准备提示) 忽略字典附件的非本地 URL: {url_value}")
            # 同时将字典中可能的纯文本说明拼入
            if isinstance(content.get('text'), str):
                text_parts.append(content.get('text'))
            content_str = "\n".join(text_parts).strip()
        else:
            logger.warning(f"[{req_id}] (准备提示) 警告: 角色 {role} 在索引 {i} 的内容类型意外 ({type(content)}) 或为 None。")
            content_str = str(content or "").strip()
        
        if content_str:
            current_turn_parts.append(content_str)
        
        # 处理工具调用（不在此处主动执行，只做可视化，避免与对话式循环的客户端执行冲突）
        tool_calls = msg.tool_calls
        if role == 'assistant' and tool_calls:
            if content_str:
                current_turn_parts.append("\n")
            
            tool_call_visualizations = []
            for tool_call in tool_calls:
                if hasattr(tool_call, 'type') and tool_call.type == 'function':
                    function_call = tool_call.function
                    func_name = function_call.name if function_call else None
                    func_args_str = function_call.arguments if function_call else None
                    
                    try:
                        parsed_args = json.loads(func_args_str if func_args_str else '{}')
                        formatted_args = json.dumps(parsed_args, indent=2, ensure_ascii=False)
                    except (json.JSONDecodeError, TypeError):
                        formatted_args = func_args_str if func_args_str is not None else "{}"
                    
                    tool_call_visualizations.append(
                        f"请求调用函数: {func_name}\n参数:\n{formatted_args}"
                    )
            
            if tool_call_visualizations:
                current_turn_parts.append("\n".join(tool_call_visualizations))

        # 处理工具结果消息（role = 'tool'）：将其纳入提示，便于模型看到工具返回
        if role == 'tool':
            tool_result_lines: List[str] = []
            # 标准 OpenAI 样式：content 为字符串，tool_call_id 关联上一轮调用
            tool_call_id = getattr(msg, 'tool_call_id', None)
            if tool_call_id:
                tool_result_lines.append(f"工具结果 (tool_call_id={tool_call_id}):")
            if isinstance(msg.content, str):
                tool_result_lines.append(msg.content)
            elif isinstance(msg.content, list):
                # 兼容少数客户端把结果装在列表里
                try:
                    merged = "\n".join(
                        it.get('text') if isinstance(it, dict) and it.get('type') == 'text' else str(it)
                        for it in msg.content
                    )
                    tool_result_lines.append(merged)
                except Exception:
                    tool_result_lines.append(str(msg.content))
            else:
                tool_result_lines.append(str(msg.content))
            if tool_result_lines:
                if content_str:
                    current_turn_parts.append("\n")
                current_turn_parts.append("\n".join(tool_result_lines))
        
        if len(current_turn_parts) > 1 or (role == 'assistant' and tool_calls):
            combined_parts.append("".join(current_turn_parts))
        elif not combined_parts and not current_turn_parts:
            logger.info(f"[{req_id}] (准备提示) 跳过角色 {role} 在索引 {i} 的空消息 (且无工具调用)。")
        elif len(current_turn_parts) == 1 and not combined_parts:
            logger.info(f"[{req_id}] (准备提示) 跳过角色 {role} 在索引 {i} 的空消息 (只有前缀)。")
    
    final_prompt = "".join(combined_parts)
    if final_prompt:
        final_prompt += "\n"
    
    preview_text = final_prompt[:300].replace('\n', '\\n')
    logger.info(f"[{req_id}] (准备提示) 组合提示长度: {len(final_prompt)}，附件数量: {len(files_list)}。Preview: '{preview_text}...'")
    
    return final_prompt, files_list


def _extract_json_from_text(text: str) -> Optional[str]:
    """尝试从纯文本中提取首个 JSON 对象字符串。"""
    if not text:
        return None
    # 简单启发式：找到第一个 '{' 与最后一个匹配的 '}'
    try:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end+1].strip()
            json.loads(candidate)
            return candidate
    except Exception:
        return None
    return None


def _get_latest_user_text(messages: List[Message]) -> str:
    """提取最近一条用户消息的文本内容（拼接多段 text）。"""
    for msg in reversed(messages):
        if msg.role == 'user':
            content = msg.content
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                parts: List[str] = []
                for it in content:
                    if isinstance(it, dict) and it.get('type') == 'text':
                        parts.append(it.get('text') or '')
                    elif hasattr(it, 'type') and it.type == 'text':
                        parts.append(getattr(it, 'text', '') or '')
                return "\n".join(p for p in parts if p)
            else:
                return ''
    return ''


async def maybe_execute_tools(messages: List[Message], tools: Optional[List[Dict[str, Any]]], tool_choice: Optional[Union[str, Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """
    基于 tools/tool_choice 的主动函数执行：
    - 若 tool_choice 指明函数名（字符串或 {type:'function', function:{name}}），则尝试执行该函数；
    - 若 tool_choice 为 'auto' 且仅提供一个工具，则执行该工具；
    - 参数来源：从最近一条用户消息的文本中尝试提取 JSON；若失败则使用空参数。
    - 返回 [{name, arguments, result}]；如无可执行则返回 None。
    """
    try:
        # Track runtime-declared tools和可选 MCP 端点
        mcp_ep = None
        # support per-request MCP endpoint via request-level message or tool spec extension (if present later)
        # current: read from env only in registry when not provided
        register_runtime_tools(tools, mcp_ep)
        # 若已有工具结果消息（role='tool'），遵循对话式调用循环，由客户端驱动，服务器不主动再次执行
        for m in messages:
            if getattr(m, 'role', None) == 'tool':
                return None
        chosen_name: Optional[str] = None
        if isinstance(tool_choice, dict):
            fn = tool_choice.get('function') if tool_choice else None
            if isinstance(fn, dict):
                chosen_name = fn.get('name')
        elif isinstance(tool_choice, str):
            lc = tool_choice.lower()
            if lc in ('none', 'no', 'off'):
                return None
            if lc in ('auto', 'required', 'any'):
                if isinstance(tools, list) and len(tools) == 1:
                    chosen_name = tools[0].get('function', {}).get('name') or tools[0].get('name')
            else:
                chosen_name = tool_choice
        elif tool_choice is None:
            # 不主动执行
            return None

        if not chosen_name:
            return None

        user_text = _get_latest_user_text(messages)
        args_json = _extract_json_from_text(user_text) or '{}'
        import asyncio
        result_str = await execute_tool_call(chosen_name, args_json)
        return [{"name": chosen_name, "arguments": args_json, "result": result_str}]
    except Exception:
        return None


## tokens moved to utils_ext.tokens


def generate_sse_stop_chunk_with_usage(req_id: str, model: str, usage_stats: dict, reason: str = "stop") -> str:
    """生成带usage统计的SSE停止块"""
    return generate_sse_stop_chunk(req_id, model, reason, usage_stats) 
