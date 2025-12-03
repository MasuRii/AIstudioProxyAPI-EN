/**
 * Chat Message Sending
 * Handles sending messages to the AI and processing streaming responses
 */

import { dom } from '../dom.js';
import { state } from '../state.js';
import { API_URL } from '../constants.js';
import { autoResizeTextarea } from '../helpers.js';
import { displayMessage, renderMessageContent, isChatScrolledToBottom, scrollChatToBottom } from './display.js';
import { saveChatHistory } from './history.js';
import { computeReasoningEffort } from '../models/thinking.js';

/**
 * Get a valid API key (placeholder - needs to be implemented)
 * @returns {Promise<string|null>} API key or null
 */
async function getValidApiKey() {
    // TODO: Implement API key retrieval logic
    // For now, return null to use unauthenticated mode
    return null;
}

/**
 * Send a chat message to the AI
 * @param {Function} addLogEntry - Log function to report status
 * @returns {Promise<void>}
 */
export async function sendMessage(addLogEntry) {
    const messageText = dom.userInput.value.trim();
    if (!messageText) {
        if (addLogEntry) {
            addLogEntry('[警告] 消息内容为空，无法发送');
        }
        return;
    }

    // Double-check input wasn't cleared during processing
    if (!dom.userInput.value.trim()) {
        if (addLogEntry) {
            addLogEntry('[警告] 输入框内容已被清空，取消发送');
        }
        return;
    }

    // Disable controls during send
    dom.userInput.disabled = true;
    dom.sendButton.disabled = true;
    dom.clearButton.disabled = true;

    try {
        // Add user message to history
        state.conversationHistory.push({ role: 'user', content: messageText });
        displayMessage(messageText, 'user', state.conversationHistory.length - 1);

        // Clear input
        dom.userInput.value = '';
        autoResizeTextarea(dom.userInput);
        saveChatHistory(addLogEntry);

        // Create streaming assistant message
        const assistantMsgElement = displayMessage('', 'assistant', state.conversationHistory.length);
        assistantMsgElement.classList.add('streaming');
        scrollChatToBottom();

        // Build request body
        let fullResponse = '';
        const requestBody = {
            messages: state.conversationHistory,
            model: state.selectedModel,
            stream: true,
            temperature: state.modelSettings.temperature,
            max_output_tokens: state.modelSettings.maxOutputTokens,
            top_p: state.modelSettings.topP,
        };

        // Add reasoning effort
        requestBody.reasoning_effort = computeReasoningEffort(state.modelSettings);

        // Add tools if enabled
        const tools = [];
        if (dom.enableGoogleSearchToggle && dom.enableGoogleSearchToggle.checked) {
            tools.push({ google_search_retrieval: {} });
        }
        if (tools.length > 0) {
            requestBody.tools = tools;
            requestBody.tool_choice = 'auto';
        }

        // Add stop sequences
        if (state.modelSettings.stopSequences) {
            const stopArray = state.modelSettings.stopSequences
                .split(',')
                .map(seq => seq.trim())
                .filter(seq => seq.length > 0);
            if (stopArray.length > 0) requestBody.stop = stopArray;
        }

        if (addLogEntry) {
            addLogEntry(
                `[信息] 发送请求，模型: ${state.selectedModel}, ` +
                `温度: ${requestBody.temperature ?? '默认'}, ` +
                `最大Token: ${requestBody.max_output_tokens ?? '默认'}, ` +
                `Top P: ${requestBody.top_p ?? '默认'}, ` +
                `思考参数: ${String(requestBody.reasoning_effort)}, ` +
                `工具: ${JSON.stringify(requestBody.tools || [])}`
            );
        }

        // Get API key for authentication
        const apiKey = await getValidApiKey();
        const headers = { 'Content-Type': 'application/json' };
        if (apiKey) {
            headers['Authorization'] = `Bearer ${apiKey}`;
        } else {
            // If no API key available, throw error
            throw new Error('无法获取有效的API密钥。请在设置页面验证密钥后再试。');
        }

        // Send request
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(requestBody)
        });

        // Handle HTTP errors
        if (!response.ok) {
            let errorText = `HTTP Error: ${response.status} ${response.statusText}`;
            try {
                const errorData = await response.json();
                errorText = errorData.detail || errorData.error?.message || errorText;
            } catch (e) {
                // Ignore parse errors
            }

            // Special handling for 401 authentication errors
            if (response.status === 401) {
                errorText = '身份验证失败：API密钥无效或缺失。请检查API密钥配置。';
                if (addLogEntry) {
                    addLogEntry('[错误] 401认证失败 - 请检查API密钥设置');
                }
            }

            throw new Error(errorText);
        }

        // Process streaming response
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            let boundary;

            while ((boundary = buffer.indexOf('\n\n')) >= 0) {
                const line = buffer.substring(0, boundary).trim();
                buffer = buffer.substring(boundary + 2);

                if (line.startsWith('data: ')) {
                    const data = line.substring(6).trim();
                    if (data === '[DONE]') continue;

                    try {
                        const chunk = JSON.parse(data);
                        if (chunk.error) {
                            throw new Error(chunk.error.message || "Unknown stream error");
                        }

                        const delta = chunk.choices?.[0]?.delta?.content || '';
                        if (delta) {
                            fullResponse += delta;
                            const wasScrolledToBottom = isChatScrolledToBottom();
                            const contentElement = assistantMsgElement.querySelector('.message-content');
                            if (contentElement) {
                                contentElement.textContent += delta;
                            }
                            if (wasScrolledToBottom) scrollChatToBottom();
                        }
                    } catch (e) {
                        if (addLogEntry) {
                            addLogEntry(`[错误] 解析流数据块失败: ${e.message}. 数据: ${data}`);
                        }
                    }
                }
            }
        }

        // Render final formatted content
        const contentElement = assistantMsgElement.querySelector('.message-content');
        if (contentElement) {
            renderMessageContent(contentElement, fullResponse);
        }

        // Save response or rollback if empty
        if (fullResponse) {
            state.conversationHistory.push({ role: 'assistant', content: fullResponse });
            saveChatHistory(addLogEntry);
        } else {
            // Remove empty assistant message
            assistantMsgElement.remove();

            // Rollback user message if AI didn't respond
            if (state.conversationHistory.at(-1)?.role === 'user') {
                state.conversationHistory.pop();
                saveChatHistory(addLogEntry);
                const userMessages = dom.chatbox.querySelectorAll('.user-message');
                if (userMessages.length > 0) {
                    userMessages[userMessages.length - 1].remove();
                }
            }
        }
    } catch (error) {
        const errorText = `喵... 出错了: ${error.message || '未知错误'} >_<`;
        displayMessage(errorText, 'error');
        if (addLogEntry) {
            addLogEntry(`[错误] 发送消息失败: ${error.message}`);
        }

        // Remove streaming message
        const streamingMsg = dom.chatbox.querySelector('.assistant-message.streaming');
        if (streamingMsg) streamingMsg.remove();

        // Rollback user message if AI failed
        if (state.conversationHistory.at(-1)?.role === 'user') {
            state.conversationHistory.pop();
            saveChatHistory(addLogEntry);
            const userMessages = dom.chatbox.querySelectorAll('.user-message');
            if (userMessages.length > 0) {
                userMessages[userMessages.length - 1].remove();
            }
        }
    } finally {
        // Re-enable controls
        dom.userInput.disabled = false;
        dom.sendButton.disabled = false;
        dom.clearButton.disabled = false;

        // Remove streaming class from final message
        const finalAssistantMsg = Array.from(
            dom.chatbox.querySelectorAll('.assistant-message.streaming')
        ).pop();
        if (finalAssistantMsg) {
            finalAssistantMsg.classList.remove('streaming');
        }

        // Focus input and scroll
        dom.userInput.focus();
        scrollChatToBottom();
    }
}

/**
 * Bind chat send events
 * @param {Function} addLogEntry - Log function to report status
 */
export function bindSendEvents(addLogEntry) {
    if (dom.sendButton) {
        dom.sendButton.addEventListener('click', () => sendMessage(addLogEntry));
    }

    if (dom.userInput) {
        dom.userInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage(addLogEntry);
            }
        });

        // Auto-resize textarea on input
        dom.userInput.addEventListener('input', () => {
            autoResizeTextarea(dom.userInput);
        });
    }
}
