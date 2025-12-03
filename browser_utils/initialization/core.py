# --- browser_utils/initialization/core.py ---
import asyncio
import logging
import os
from typing import Any, Dict, Optional, Tuple

from playwright.async_api import (
    Browser as AsyncBrowser,
)
from playwright.async_api import (
    BrowserContext as AsyncBrowserContext,
)
from playwright.async_api import (
    Error as PlaywrightAsyncError,
)
from playwright.async_api import (
    Page as AsyncPage,
)
from playwright.async_api import (
    expect as expect_async,
)

from config import (
    AI_STUDIO_URL_PATTERN,
    INPUT_SELECTOR,
    USER_INPUT_END_MARKER_SERVER,
    USER_INPUT_START_MARKER_SERVER,
    GlobalState,
)

from .auth import wait_for_model_list_and_handle_auth_save
from .debug import setup_debug_listeners
from .network import setup_network_interception_and_scripts

logger = logging.getLogger("AIStudioProxyServer")


async def _wait_for_shutdown():
    """Helper to wait for GlobalState.IS_SHUTTING_DOWN event."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, GlobalState.IS_SHUTTING_DOWN.wait)


async def initialize_page_logic(
    browser: AsyncBrowser, storage_state_path: Optional[str] = None
) -> Tuple[AsyncPage, bool]:
    """
    初始化页面逻辑，连接到现有浏览器

    Args:
        browser: Playwright 浏览器实例
        storage_state_path: 可选的认证文件路径。如果提供，将优先使用此路径。
    """
    logger.info("--- 初始化页面逻辑 (连接到现有浏览器) ---")
    temp_context: Optional[AsyncBrowserContext] = None
    storage_state_path_to_use: Optional[str] = None
    launch_mode = os.environ.get("LAUNCH_MODE", "debug")
    logger.info(f"   检测到启动模式: {launch_mode}")
    loop = asyncio.get_running_loop()

    # 优先使用传入的 storage_state_path
    if storage_state_path:
        if os.path.exists(storage_state_path):
            storage_state_path_to_use = storage_state_path
            logger.info(f"   使用指定的认证文件: {storage_state_path_to_use}")
        else:
            logger.error(f"指定的认证文件不存在: {storage_state_path}")
            # 如果是明确指定的路径但不存在，这应该是一个错误
            raise RuntimeError(f"指定的认证文件不存在: {storage_state_path}")
    else:
        # 回退到原有的环境变量逻辑
        if launch_mode == "headless" or launch_mode == "virtual_headless":
            # Check for Auto-Auth Rotation on Startup
            if os.environ.get('AUTO_AUTH_ROTATION_ON_STARTUP', 'false').lower() == 'true':
                logger.info("   🤖 Auto-Auth Rotation on Startup is ENABLED. Selecting profile...")
                try:
                    # Local import to avoid circular dependencies
                    from browser_utils.auth_rotation import _get_next_profile
                    next_profile = _get_next_profile()
                    if next_profile:
                        os.environ['ACTIVE_AUTH_JSON_PATH'] = next_profile
                        logger.info(f"   ✅ Auto-selected profile: {next_profile}")
                    else:
                        logger.warning("   ⚠️ Auto-Auth Rotation: No available profiles found. Continuing with environment defaults.")
                except ImportError:
                    logger.error("   ❌ Auto-Auth Rotation failed: Could not import auth_rotation module.")
                except Exception as e:
                    logger.error(f"   ❌ Error during Auto-Auth Rotation on Startup: {e}", exc_info=True)

            auth_filename = os.environ.get("ACTIVE_AUTH_JSON_PATH")
            logger.info(f"[DEBUG] Headless Init: ACTIVE_AUTH_JSON_PATH='{auth_filename}'")

            if auth_filename:
                constructed_path = auth_filename
                if os.path.exists(constructed_path):
                    storage_state_path_to_use = constructed_path
                    logger.info(f"   无头模式将使用的认证文件: {constructed_path}")
                else:
                    logger.error(
                        f"{launch_mode} 模式认证文件无效或不存在: '{constructed_path}'"
                    )
                    # DIAGNOSTIC: Check if we should have rotated
                    logger.info(f"[DEBUG] Auth file missing. Auto-Rotation Flag: {os.environ.get('AUTO_AUTH_ROTATION_ON_STARTUP')}")
                    raise RuntimeError(
                        f"{launch_mode} 模式认证文件无效: '{constructed_path}'"
                    )
            else:
                logger.error(
                    f"{launch_mode} 模式需要 ACTIVE_AUTH_JSON_PATH 环境变量，但未设置或为空。"
                )
                raise RuntimeError(f"{launch_mode} 模式需要 ACTIVE_AUTH_JSON_PATH。")
        elif launch_mode == "debug":
            logger.info(
                "   调试模式: 尝试从环境变量 ACTIVE_AUTH_JSON_PATH 加载认证文件..."
            )
            auth_filepath_from_env = os.environ.get("ACTIVE_AUTH_JSON_PATH")
            if auth_filepath_from_env and os.path.exists(auth_filepath_from_env):
                storage_state_path_to_use = auth_filepath_from_env
                logger.info(
                    f"   调试模式将使用的认证文件 (来自环境变量): {storage_state_path_to_use}"
                )
            elif auth_filepath_from_env:
                logger.warning(
                    f"   调试模式下环境变量 ACTIVE_AUTH_JSON_PATH 指向的文件不存在: '{auth_filepath_from_env}'。不加载认证文件。"
                )
            else:
                logger.info(
                    "   调试模式下未通过环境变量提供认证文件。将使用浏览器当前状态。"
                )
        elif launch_mode == "direct_debug_no_browser":
            logger.info(
                "   direct_debug_no_browser 模式：不加载 storage_state，不进行浏览器操作。"
            )
        else:
            logger.warning(
                f"   警告: 未知的启动模式 '{launch_mode}'。不加载 storage_state。"
            )

    try:
        logger.info("创建新的浏览器上下文...")
        context_options: Dict[str, Any] = {"viewport": {"width": 460, "height": 800}}
        if storage_state_path_to_use:
            context_options["storage_state"] = storage_state_path_to_use
            import server
            server.current_auth_profile_path = storage_state_path_to_use
            logger.info(
                f"   (使用 storage_state='{os.path.basename(storage_state_path_to_use)}')"
            )
        else:
            import server
            server.current_auth_profile_path = None
            logger.info("   (不使用 storage_state)")

        # 代理设置需要从server模块中获取
        import server

        if server.PLAYWRIGHT_PROXY_SETTINGS:
            context_options["proxy"] = server.PLAYWRIGHT_PROXY_SETTINGS
            logger.info(
                f"   (浏览器上下文将使用代理: {server.PLAYWRIGHT_PROXY_SETTINGS['server']})"
            )
        else:
            logger.info("   (浏览器上下文不使用显式代理配置)")

        context_options["ignore_https_errors"] = True
        logger.info("   (浏览器上下文将忽略 HTTPS 错误)")

        temp_context = await browser.new_context(**context_options)

        # 设置网络拦截和脚本注入
        await setup_network_interception_and_scripts(temp_context)

        found_page: Optional[AsyncPage] = None
        pages = temp_context.pages
        target_url_base = f"https://{AI_STUDIO_URL_PATTERN}"
        target_full_url = f"{target_url_base}prompts/new_chat"
        login_url_pattern = "accounts.google.com"
        current_url = ""

        # 导入_handle_model_list_response - 需要延迟导入避免循环引用
        from browser_utils.operations import _handle_model_list_response

        for p_iter in pages:
            try:
                page_url_to_check = p_iter.url
                if (
                    not p_iter.is_closed()
                    and target_url_base in page_url_to_check
                    and "/prompts/" in page_url_to_check
                ):
                    found_page = p_iter
                    current_url = page_url_to_check
                    logger.info(f"   找到已打开的 AI Studio 页面: {current_url}")
                    if found_page:
                        logger.info(
                            f"   为已存在的页面 {found_page.url} 添加模型列表响应监听器。"
                        )
                        found_page.on("response", _handle_model_list_response)
                        # Setup debug listeners for error snapshots
                        setup_debug_listeners(found_page)
                    break
            except PlaywrightAsyncError as pw_err_url:
                logger.warning(f"   检查页面 URL 时出现 Playwright 错误: {pw_err_url}")
            except AttributeError as attr_err_url:
                logger.warning(f"   检查页面 URL 时出现属性错误: {attr_err_url}")
            except asyncio.CancelledError:
                raise
            except Exception as e_url_check:
                logger.warning(
                    f"   检查页面 URL 时出现其他未预期错误: {e_url_check} (类型: {type(e_url_check).__name__})"
                )

        if not found_page:
            logger.info(
                f"-> 未找到合适的现有页面，正在打开新页面并导航到 {target_full_url}..."
            )
            found_page = await temp_context.new_page()
            if found_page:
                logger.info("   为新创建的页面添加模型列表响应监听器 (导航前)。")
                found_page.on("response", _handle_model_list_response)
                # Setup debug listeners for error snapshots
                setup_debug_listeners(found_page)
            try:
                await found_page.goto(
                    target_full_url, wait_until="domcontentloaded", timeout=90000
                )
                current_url = found_page.url
                logger.info(f"-> 新页面导航尝试完成。当前 URL: {current_url}")
            except asyncio.CancelledError:
                raise
            except Exception as new_page_nav_err:
                # 导入save_error_snapshot函数
                from browser_utils.operations import save_error_snapshot

                await save_error_snapshot("init_new_page_nav_fail")
                error_str = str(new_page_nav_err)
                if "NS_ERROR_NET_INTERRUPT" in error_str:
                    logger.error("\n" + "=" * 30 + " 网络导航错误提示 " + "=" * 30)
                    logger.error(
                        f"导航到 '{target_full_url}' 失败，出现网络中断错误 (NS_ERROR_NET_INTERRUPT)。"
                    )
                    logger.error("   这通常表示浏览器在尝试加载页面时连接被意外断开。")
                    logger.error("   可能的原因及排查建议:")
                    logger.error(
                        "     1. 网络连接: 请检查你的本地网络连接是否稳定，并尝试在普通浏览器中访问目标网址。"
                    )
                    logger.error(
                        "     2. AI Studio 服务: 确认 aistudio.google.com 服务本身是否可用。"
                    )
                    logger.error(
                        "     3. 防火墙/代理/VPN: 检查本地防火墙、杀毒软件、代理或 VPN 设置。"
                    )
                    logger.error(
                        "     4. Camoufox 服务: 确认 launch_camoufox.py 脚本是否正常运行。"
                    )
                    logger.error(
                        "     5. 系统资源问题: 确保系统有足够的内存和 CPU 资源。"
                    )
                    logger.error("=" * 74 + "\n")
                raise RuntimeError(
                    f"导航新页面失败: {new_page_nav_err}"
                ) from new_page_nav_err

        if login_url_pattern in current_url:
            if launch_mode == "headless":
                logger.error(
                    "无头模式下检测到重定向至登录页面，认证可能已失效。请更新认证文件。"
                )
                raise RuntimeError("无头模式认证失败，需要更新认证文件。")
            else:
                print(f"\n{'=' * 20} 需要操作 {'=' * 20}", flush=True)
                login_prompt = "   检测到可能需要登录。如果浏览器显示登录页面，请在浏览器窗口中完成 Google 登录，然后在此处按 Enter 键继续..."
                # NEW: If SUPPRESS_LOGIN_WAIT is set, skip waiting for user input.
                if os.environ.get("SUPPRESS_LOGIN_WAIT", "").lower() in (
                    "1",
                    "true",
                    "yes",
                ):
                    logger.info("检测到 SUPPRESS_LOGIN_WAIT 标志，跳过等待用户输入。")
                else:
                    print(USER_INPUT_START_MARKER_SERVER, flush=True)
                    await loop.run_in_executor(None, input, login_prompt)
                    print(USER_INPUT_END_MARKER_SERVER, flush=True)
                logger.info("   正在检查登录状态...")
                try:
                    await found_page.wait_for_url(
                        f"**/{AI_STUDIO_URL_PATTERN}**", timeout=180000
                    )
                    current_url = found_page.url
                    if login_url_pattern in current_url:
                        logger.error("手动登录尝试后，页面似乎仍停留在登录页面。")
                        raise RuntimeError("手动登录尝试后仍在登录页面。")
                    logger.info("   登录成功！请不要操作浏览器窗口，等待后续提示。")

                    # 登录成功后，调用认证保存逻辑
                    if os.environ.get("AUTO_SAVE_AUTH", "false").lower() == "true":
                        await wait_for_model_list_and_handle_auth_save(
                            temp_context, launch_mode, loop
                        )

                except asyncio.CancelledError:
                    raise
                except Exception as wait_login_err:
                    from browser_utils.operations import save_error_snapshot

                    await save_error_snapshot("init_login_wait_fail")
                    logger.error(
                        f"登录提示后未能检测到 AI Studio URL 或保存状态时出错: {wait_login_err}",
                        exc_info=True,
                    )
                    raise RuntimeError(
                        f"登录提示后未能检测到 AI Studio URL: {wait_login_err}"
                    ) from wait_login_err

        elif target_url_base not in current_url or "/prompts/" not in current_url:
            from browser_utils.operations import save_error_snapshot

            await save_error_snapshot("init_unexpected_page")
            logger.error(
                f"初始导航后页面 URL 意外: {current_url}。期望包含 '{target_url_base}' 和 '/prompts/'。"
            )
            raise RuntimeError(f"初始导航后出现意外页面: {current_url}。")

        logger.info(f"-> 确认当前位于 AI Studio 对话页面: {current_url}")
        await found_page.bring_to_front()

        try:
            input_wrapper_locator = found_page.locator("ms-prompt-input-wrapper")
            
            # Wait for either input visibility or shutdown signal
            expect_task = asyncio.create_task(expect_async(input_wrapper_locator).to_be_visible(timeout=35000))
            shutdown_task = asyncio.create_task(_wait_for_shutdown())

            done, pending = await asyncio.wait([expect_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED)

            if shutdown_task in done:
                logger.info("🛑 Shutdown signal received during initialization. Aborting.")
                expect_task.cancel()
                raise RuntimeError("Initialization aborted due to shutdown signal.")

            # expect_task finished
            shutdown_task.cancel()
            await expect_task # Propagate result/exception

            await expect_async(found_page.locator(INPUT_SELECTOR)).to_be_visible(
                timeout=10000
            )
            logger.info("-> 核心输入区域可见。")

            model_name_locator = found_page.locator('[data-test-id="model-name"]')
            try:
                model_name_on_page = await model_name_locator.first.inner_text(
                    timeout=5000
                )
                logger.info(f"-> 页面检测到的当前模型: {model_name_on_page}")
            except PlaywrightAsyncError as e:
                logger.error(f"获取模型名称时出错 (model_name_locator): {e}")
                raise

            result_page_instance = found_page
            result_page_ready = True

            # 脚本注入已在上下文创建时完成，无需在此处重复注入

            logger.info("页面逻辑初始化成功。")
            return result_page_instance, result_page_ready
        except asyncio.CancelledError:
            raise
        except Exception as input_visible_err:
            from browser_utils.operations import save_error_snapshot

            await save_error_snapshot("init_fail_input_timeout")
            logger.error(
                f"页面初始化失败：核心输入区域未在预期时间内变为可见。最后的 URL 是 {found_page.url}",
                exc_info=True,
            )
            raise RuntimeError(
                f"页面初始化失败：核心输入区域未在预期时间内变为可见。最后的 URL 是 {found_page.url}"
            ) from input_visible_err
    except asyncio.CancelledError:
        logger.warning("页面初始化被取消。")
        if temp_context:
            try:
                await temp_context.close()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
        raise
    except Exception as e_init_page:
        logger.critical(
            f"页面逻辑初始化期间发生严重意外错误: {e_init_page}", exc_info=True
        )
        if temp_context:
            try:
                logger.info(
                    "   尝试关闭临时的浏览器上下文 due to initialization error."
                )
                # [ID-04] Optimize Browser Lifecycle Management: Add timeout to context close
                await asyncio.wait_for(temp_context.close(), timeout=2.0)
                logger.info("   临时浏览器上下文已关闭。")
            except asyncio.TimeoutError:
                logger.warning("   🚨 [ID-04] 浏览器上下文关闭超时 (2s), 跳过强制关闭以加快关闭速度.")
            except asyncio.CancelledError:
                raise
            except Exception as close_err:
                logger.warning(f"   关闭临时浏览器上下文时出错: {close_err}")
        from browser_utils.operations import save_error_snapshot

        await save_error_snapshot("init_unexpected_error")
        raise RuntimeError(f"页面初始化意外错误: {e_init_page}") from e_init_page


async def close_page_logic() -> Tuple[None, bool]:
    """关闭页面逻辑"""
    # 需要访问全局变量
    from api_utils.server_state import state

    logger.info("--- 运行页面逻辑关闭 --- ")
    if state.page_instance and not state.page_instance.is_closed():
        try:
            # [ID-04] Optimize Browser Lifecycle Management: 2-second timeout for graceful close
            await asyncio.wait_for(state.page_instance.close(), timeout=2.0)
            logger.info("   页面已关闭")
        except asyncio.TimeoutError:
            logger.warning("   🚨 [ID-04] 浏览器页面关闭超时 (2s), 跳过强制关闭以加快关闭速度.")
        except PlaywrightAsyncError as pw_err:
            logger.warning(f"   关闭页面时出现Playwright错误: {pw_err}")
        except asyncio.TimeoutError as timeout_err:
            logger.warning(f"   关闭页面时超时: {timeout_err}")
        except asyncio.CancelledError:
            raise
        except Exception as other_err:
            logger.error(
                f"   关闭页面时出现意外错误: {other_err} (类型: {type(other_err).__name__})",
                exc_info=True,
            )
    state.page_instance = None
    state.is_page_ready = False
    logger.info("页面逻辑状态已重置。")
    return None, False


async def signal_camoufox_shutdown() -> None:
    """发送关闭信号到Camoufox服务器"""
    logger.info("   尝试发送关闭信号到 Camoufox 服务器 (此功能可能已由父进程处理)...")
    ws_endpoint = os.environ.get("CAMOUFOX_WS_ENDPOINT")
    if not ws_endpoint:
        logger.warning("   无法发送关闭信号：未找到 CAMOUFOX_WS_ENDPOINT 环境变量。")
        return

    # 需要访问全局浏览器实例
    import server

    if not server.browser_instance or not server.browser_instance.is_connected():
        logger.warning("   浏览器实例已断开或未初始化，跳过关闭信号发送。")
        return
    try:
        await asyncio.sleep(0.2)
        logger.info("   (模拟) 关闭信号已处理。")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"   发送关闭信号过程中捕获异常: {e}", exc_info=True)


async def enable_temporary_chat_mode(page: AsyncPage) -> None:
    """
    检查并启用 AI Studio 界面的“临时聊天”模式。
    这是一个独立的UI操作，应该在页面完全稳定后调用。
    """
    try:
        logger.info("-> (UI Op) 正在检查并启用 '临时聊天' 模式...")

        incognito_button_locator = page.locator(
            'button[aria-label="Temporary chat toggle"]'
        )

        await incognito_button_locator.wait_for(state="visible", timeout=10000)

        button_classes = await incognito_button_locator.get_attribute("class")

        if button_classes and "ms-button-active" in button_classes:
            logger.info("-> (UI Op) '临时聊天' 模式已激活。")
        else:
            logger.info("-> (UI Op) '临时聊天' 模式未激活，正在点击...")
            await incognito_button_locator.click(timeout=5000, force=True)
            await asyncio.sleep(1)

            updated_classes = await incognito_button_locator.get_attribute("class")
            if updated_classes and "ms-button-active" in updated_classes:
                logger.info("(UI Op) '临时聊天' 模式已成功启用。")
            else:
                logger.warning("(UI Op) 点击后 '临时聊天' 模式状态验证失败。")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"(UI Op) 启用 '临时聊天' 模式时出错: {e}")
