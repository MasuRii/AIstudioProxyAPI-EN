/**
 * Chat History Management
 * Handles saving and loading chat history from localStorage
 */

import { dom } from '../dom.js';
import { state } from '../state.js';
import { CHAT_HISTORY_KEY } from '../constants.js';
import { setLocalStorage, getLocalStorage, safeJSONParse, safeJSONStringify } from '../helpers.js';
import { displayMessage, clearChatDisplay } from './display.js';

/**
 * Save conversation history to localStorage
 * @param {Function} addLogEntry - Log function to report status
 */
export function saveChatHistory(addLogEntry) {
    try {
        setLocalStorage(CHAT_HISTORY_KEY, safeJSONStringify(state.conversationHistory));
    } catch (e) {
        if (addLogEntry) {
            addLogEntry("[错误] 保存聊天记录失败。");
        }
    }
}

/**
 * Load conversation history from localStorage
 * @param {Function} addLogEntry - Log function to report status
 * @returns {boolean} True if history was loaded successfully
 */
export function loadChatHistory(addLogEntry) {
    try {
        const storedHistory = getLocalStorage(CHAT_HISTORY_KEY);
        if (storedHistory) {
            const parsedHistory = safeJSONParse(storedHistory, null);
            if (Array.isArray(parsedHistory) && parsedHistory.length > 0) {
                // Ensure the current system prompt is used
                parsedHistory[0] = {
                    role: "system",
                    content: state.modelSettings.systemPrompt
                };
                state.conversationHistory = parsedHistory;

                // Clear chatbox before re-rendering
                clearChatDisplay();

                // Display messages
                for (let i = 0; i < state.conversationHistory.length; i++) {
                    // Display system message only if it's the first one
                    if (i === 0 && state.conversationHistory[i].role === 'system') {
                        displayMessage(
                            state.conversationHistory[i].content,
                            state.conversationHistory[i].role,
                            i
                        );
                    } else if (state.conversationHistory[i].role !== 'system') {
                        displayMessage(
                            state.conversationHistory[i].content,
                            state.conversationHistory[i].role,
                            i
                        );
                    }
                }

                if (addLogEntry) {
                    addLogEntry("[信息] 从 localStorage 加载了聊天记录。");
                }
                return true;
            }
        }
    } catch (e) {
        if (addLogEntry) {
            addLogEntry("[错误] 加载聊天记录失败。");
        }
        localStorage.removeItem(CHAT_HISTORY_KEY);
    }
    return false;
}

/**
 * Clear chat history from state and localStorage
 * @param {Function} addLogEntry - Log function to report status
 */
export function clearChatHistory(addLogEntry) {
    // Reset conversation history to just system prompt
    state.conversationHistory = [{
        role: "system",
        content: state.modelSettings.systemPrompt
    }];

    // Clear UI
    clearChatDisplay();

    // Display system prompt
    displayMessage(state.modelSettings.systemPrompt, 'system', 0);

    // Save to localStorage
    saveChatHistory(addLogEntry);

    if (addLogEntry) {
        addLogEntry("[信息] 聊天记录已清除。");
    }
}

/**
 * Initialize chat with system prompt
 * @param {Function} addLogEntry - Log function to report status
 */
export function initializeChatHistory(addLogEntry) {
    // Start with system prompt
    state.conversationHistory = [{
        role: "system",
        content: state.modelSettings.systemPrompt
    }];

    // Clear chatbox
    clearChatDisplay();

    // Try to load saved history
    const historyLoaded = loadChatHistory(addLogEntry);

    // If no history or only system prompt, display current system prompt
    if (!historyLoaded || state.conversationHistory.length <= 1) {
        displayMessage(state.modelSettings.systemPrompt, 'system', 0);
    }
}
