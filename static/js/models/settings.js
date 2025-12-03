/**
 * Model Settings Management
 * Handles saving, loading, and resetting model settings
 */

import { dom } from '../dom.js';
import { state } from '../state.js';
import { DEFAULT_SYSTEM_PROMPT, MODEL_SETTINGS_KEY } from '../constants.js';
import { setLocalStorage, getLocalStorage, safeJSONParse, safeJSONStringify } from '../helpers.js';
import { updateThinkingControlsVisibility } from './thinking.js';
import { updateControlsForSelectedModel } from './list.js';

/**
 * Initialize model settings from localStorage
 * @param {Function} addLogEntry - Log function to report status
 */
export function initializeModelSettings(addLogEntry) {
    try {
        const storedSettings = getLocalStorage(MODEL_SETTINGS_KEY);
        if (storedSettings) {
            const parsedSettings = safeJSONParse(storedSettings, null);
            if (parsedSettings) {
                state.modelSettings = { ...state.modelSettings, ...parsedSettings };
            }
        }
    } catch (e) {
        if (addLogEntry) {
            addLogEntry("[错误] 加载模型设置失败。");
        }
    }
    updateModelSettingsUI();
}

/**
 * Update UI to reflect current model settings
 */
export function updateModelSettingsUI() {
    if (dom.systemPromptInput) {
        dom.systemPromptInput.value = state.modelSettings.systemPrompt;
    }
    if (dom.temperatureSlider) {
        dom.temperatureSlider.value = state.modelSettings.temperature;
    }
    if (dom.temperatureValue) {
        dom.temperatureValue.value = state.modelSettings.temperature;
    }
    if (dom.maxOutputTokensSlider) {
        dom.maxOutputTokensSlider.value = state.modelSettings.maxOutputTokens;
    }
    if (dom.maxOutputTokensValue) {
        dom.maxOutputTokensValue.value = state.modelSettings.maxOutputTokens;
    }
    if (dom.topPSlider) {
        dom.topPSlider.value = state.modelSettings.topP;
    }
    if (dom.topPValue) {
        dom.topPValue.value = state.modelSettings.topP;
    }
    if (dom.stopSequencesInput) {
        dom.stopSequencesInput.value = state.modelSettings.stopSequences;
    }
    if (dom.enableThinkingToggle) {
        dom.enableThinkingToggle.checked = !!state.modelSettings.enableThinking;
    }
    if (dom.thinkingLevelSelector) {
        dom.thinkingLevelSelector.value = state.modelSettings.thinkingLevel || "";
    }
    if (dom.enableManualBudgetToggle) {
        dom.enableManualBudgetToggle.checked = !!state.modelSettings.enableManualBudget;
    }
    if (dom.thinkingBudgetSlider) {
        dom.thinkingBudgetSlider.value = state.modelSettings.thinkingBudget;
    }
    if (dom.thinkingBudgetValue) {
        dom.thinkingBudgetValue.value = state.modelSettings.thinkingBudget;
    }
    if (dom.enableGoogleSearchToggle) {
        dom.enableGoogleSearchToggle.checked = !!state.modelSettings.enableGoogleSearch;
    }

    // Update thinking controls visibility based on model and thinking mode state
    updateThinkingControlsVisibility();
}

/**
 * Save current model settings to localStorage and update chat history
 * @param {Function} addLogEntry - Log function to report status
 * @param {Function} saveChatHistory - Function to save chat history
 * @param {Function} renderMessageContent - Function to render message content
 */
export function saveModelSettings(addLogEntry, saveChatHistory, renderMessageContent) {
    // Read settings from UI
    if (dom.systemPromptInput) {
        state.modelSettings.systemPrompt = dom.systemPromptInput.value.trim() || DEFAULT_SYSTEM_PROMPT;
    }
    if (dom.temperatureValue) {
        state.modelSettings.temperature = parseFloat(dom.temperatureValue.value);
    }
    if (dom.maxOutputTokensValue) {
        state.modelSettings.maxOutputTokens = parseInt(dom.maxOutputTokensValue.value);
    }
    if (dom.topPValue) {
        state.modelSettings.topP = parseFloat(dom.topPValue.value);
    }
    if (dom.stopSequencesInput) {
        state.modelSettings.stopSequences = dom.stopSequencesInput.value.trim();
    }
    if (dom.enableThinkingToggle) {
        state.modelSettings.enableThinking = !!dom.enableThinkingToggle.checked;
    }
    if (dom.thinkingLevelSelector) {
        state.modelSettings.thinkingLevel = (dom.thinkingLevelSelector.value || "").toLowerCase();
    }
    if (dom.enableManualBudgetToggle) {
        state.modelSettings.enableManualBudget = !!dom.enableManualBudgetToggle.checked;
    }
    if (dom.thinkingBudgetValue) {
        const budgetVal = parseInt(dom.thinkingBudgetValue.value);
        state.modelSettings.thinkingBudget = isNaN(budgetVal) ? 8192 : budgetVal;
    }
    if (dom.enableGoogleSearchToggle) {
        state.modelSettings.enableGoogleSearch = !!dom.enableGoogleSearchToggle.checked;
    }

    try {
        // Save to localStorage
        setLocalStorage(MODEL_SETTINGS_KEY, safeJSONStringify(state.modelSettings));

        // Update system prompt in conversation history
        if (state.conversationHistory.length > 0 && state.conversationHistory[0].role === 'system') {
            if (state.conversationHistory[0].content !== state.modelSettings.systemPrompt) {
                state.conversationHistory[0].content = state.modelSettings.systemPrompt;
                if (saveChatHistory) saveChatHistory();

                // Update displayed system message if it exists
                if (dom.chatbox && renderMessageContent) {
                    const systemMsgElement = dom.chatbox.querySelector('.system-message[data-index="0"] .message-content');
                    if (systemMsgElement) {
                        renderMessageContent(systemMsgElement, state.modelSettings.systemPrompt);
                    }
                }
            }
        }

        showSettingsStatus("设置已保存！", false);
        if (addLogEntry) {
            addLogEntry("[信息] 模型设置已保存。");
        }
    } catch (e) {
        showSettingsStatus("保存设置失败！", true);
        if (addLogEntry) {
            addLogEntry("[错误] 保存模型设置失败。");
        }
    }
}

/**
 * Reset model settings to defaults for current model
 * @param {Function} addLogEntry - Log function to report status
 * @param {Function} saveChatHistory - Function to save chat history
 * @param {Function} renderMessageContent - Function to render message content
 */
export function resetModelSettings(addLogEntry, saveChatHistory, renderMessageContent) {
    if (!confirm("确定要将当前模型的参数恢复为默认值吗？系统提示词也会重置。 注意：这不会清除已保存的其他模型的设置。")) {
        return;
    }

    state.modelSettings.systemPrompt = DEFAULT_SYSTEM_PROMPT;
    if (dom.systemPromptInput) {
        dom.systemPromptInput.value = DEFAULT_SYSTEM_PROMPT;
    }

    // Apply model-specific defaults to UI and modelSettings object
    updateControlsForSelectedModel(addLogEntry);

    state.modelSettings.enableThinking = false;
    state.modelSettings.thinkingLevel = "";
    state.modelSettings.thinkingBudget = 8192;
    updateModelSettingsUI();

    try {
        // Save these model-specific defaults to localStorage
        setLocalStorage(MODEL_SETTINGS_KEY, safeJSONStringify(state.modelSettings));
        if (addLogEntry) {
            addLogEntry("[信息] 当前模型的参数已重置为默认值并保存。");
        }
        showSettingsStatus("参数已重置为当前模型的默认值！", false);
    } catch (e) {
        if (addLogEntry) {
            addLogEntry("[错误] 保存重置后的模型设置失败。");
        }
        showSettingsStatus("重置并保存设置失败！", true);
    }

    // Update system prompt in conversation history
    if (state.conversationHistory.length > 0 && state.conversationHistory[0].role === 'system') {
        if (state.conversationHistory[0].content !== state.modelSettings.systemPrompt) {
            state.conversationHistory[0].content = state.modelSettings.systemPrompt;
            if (saveChatHistory) saveChatHistory();

            if (dom.chatbox && renderMessageContent) {
                const systemMsgElement = dom.chatbox.querySelector('.system-message[data-index="0"] .message-content');
                if (systemMsgElement) {
                    renderMessageContent(systemMsgElement, state.modelSettings.systemPrompt);
                }
            }
        }
    }
}

/**
 * Show temporary status message in settings panel
 * @param {string} message - Status message to display
 * @param {boolean} isError - Whether this is an error message
 */
export function showSettingsStatus(message, isError = false) {
    if (!dom.settingsStatusElement) return;

    dom.settingsStatusElement.textContent = message;
    dom.settingsStatusElement.style.color = isError ? "var(--error-color)" : "var(--primary-color)";

    setTimeout(() => {
        dom.settingsStatusElement.textContent = "设置将在发送消息时自动应用，并保存在本地。";
        dom.settingsStatusElement.style.color = "rgba(var(--on-surface-rgb), 0.8)";
    }, 3000);
}

/**
 * Bind model settings event listeners
 * @param {Function} addLogEntry - Log function to report status
 * @param {Function} saveChatHistory - Function to save chat history
 * @param {Function} renderMessageContent - Function to render message content
 */
export function bindModelSettingsEvents(addLogEntry, saveChatHistory, renderMessageContent) {
    // Temperature slider sync
    if (dom.temperatureSlider && dom.temperatureValue) {
        dom.temperatureSlider.addEventListener('input', (e) => {
            dom.temperatureValue.value = e.target.value;
            state.modelSettings.temperature = parseFloat(e.target.value);
        });
        dom.temperatureValue.addEventListener('input', (e) => {
            dom.temperatureSlider.value = e.target.value;
            state.modelSettings.temperature = parseFloat(e.target.value);
        });
    }

    // Max tokens slider sync
    if (dom.maxOutputTokensSlider && dom.maxOutputTokensValue) {
        dom.maxOutputTokensSlider.addEventListener('input', (e) => {
            dom.maxOutputTokensValue.value = e.target.value;
            state.modelSettings.maxOutputTokens = parseInt(e.target.value);
        });
        dom.maxOutputTokensValue.addEventListener('input', (e) => {
            dom.maxOutputTokensSlider.value = e.target.value;
            state.modelSettings.maxOutputTokens = parseInt(e.target.value);
        });
    }

    // Top-p slider sync
    if (dom.topPSlider && dom.topPValue) {
        dom.topPSlider.addEventListener('input', (e) => {
            dom.topPValue.value = e.target.value;
            state.modelSettings.topP = parseFloat(e.target.value);
        });
        dom.topPValue.addEventListener('input', (e) => {
            dom.topPSlider.value = e.target.value;
            state.modelSettings.topP = parseFloat(e.target.value);
        });
    }

    // Google Search toggle
    if (dom.enableGoogleSearchToggle) {
        dom.enableGoogleSearchToggle.addEventListener('change', (e) => {
            state.modelSettings.enableGoogleSearch = e.target.checked;
        });
    }

    // Save button
    if (dom.saveModelSettingsButton) {
        dom.saveModelSettingsButton.addEventListener('click', () => {
            saveModelSettings(addLogEntry, saveChatHistory, renderMessageContent);
        });
    }

    // Reset button
    if (dom.resetModelSettingsButton) {
        dom.resetModelSettingsButton.addEventListener('click', () => {
            resetModelSettings(addLogEntry, saveChatHistory, renderMessageContent);
        });
    }
}
