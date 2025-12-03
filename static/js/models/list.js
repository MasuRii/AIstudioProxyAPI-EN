/**
 * Model List Management
 * Handles loading, selection, and configuration of AI models
 */

import { dom } from '../dom.js';
import { state } from '../state.js';
import { MODEL_NAME, SELECTED_MODEL_KEY } from '../constants.js';
import { setLocalStorage, getLocalStorage } from '../helpers.js';
import { updateThinkingControlsVisibility, updateThinkingBudgetMax } from './thinking.js';

/**
 * Load available models from API and populate selector
 * @param {Function} addLogEntry - Log function to report status
 * @returns {Promise<void>}
 */
export async function loadModelList(addLogEntry) {
    try {
        const currentSelectedModelInUI = dom.modelSelector.value || state.selectedModel;
        dom.modelSelector.disabled = true;
        dom.refreshModelsButton.disabled = true;
        dom.modelSelector.innerHTML = '<option value="">加载中...</option>';

        const response = await fetch('/v1/models');
        if (!response.ok) throw new Error(`HTTP 错误! 状态: ${response.status}`);

        const data = await response.json();
        if (!data.data || !Array.isArray(data.data)) {
            throw new Error('无效的模型数据格式');
        }

        state.allModelsData = data.data;

        dom.modelSelector.innerHTML = '';

        const defaultOption = document.createElement('option');
        defaultOption.value = MODEL_NAME;
        defaultOption.textContent = '未选择模型（默认）';
        dom.modelSelector.appendChild(defaultOption);

        state.allModelsData.forEach(model => {
            const option = document.createElement('option');
            option.value = model.id;
            option.textContent = model.display_name || model.id;
            dom.modelSelector.appendChild(option);
        });

        const savedModelId = getLocalStorage(SELECTED_MODEL_KEY);
        let modelToSelect = MODEL_NAME;

        if (savedModelId && state.allModelsData.some(m => m.id === savedModelId)) {
            modelToSelect = savedModelId;
        } else if (currentSelectedModelInUI && state.allModelsData.some(m => m.id === currentSelectedModelInUI)) {
            modelToSelect = currentSelectedModelInUI;
        }

        const finalOption = Array.from(dom.modelSelector.options).find(opt => opt.value === modelToSelect);
        if (finalOption) {
            dom.modelSelector.value = modelToSelect;
            state.selectedModel = modelToSelect;
        } else {
            if (dom.modelSelector.options.length > 1 && dom.modelSelector.options[0].value === MODEL_NAME) {
                if (dom.modelSelector.options.length > 1 && dom.modelSelector.options[1]) {
                    dom.modelSelector.selectedIndex = 1;
                } else {
                    dom.modelSelector.selectedIndex = 0;
                }
            } else if (dom.modelSelector.options.length > 0) {
                dom.modelSelector.selectedIndex = 0;
            }
            state.selectedModel = dom.modelSelector.value;
        }

        setLocalStorage(SELECTED_MODEL_KEY, state.selectedModel);
        updateControlsForSelectedModel(addLogEntry);

        if (addLogEntry) {
            addLogEntry(`[信息] 已加载 ${state.allModelsData.length} 个模型。当前选择: ${state.selectedModel}`);
        }
    } catch (error) {
        console.error('获取模型列表失败:', error);
        if (addLogEntry) {
            addLogEntry(`[错误] 获取模型列表失败: ${error.message}`);
        }
        state.allModelsData = [];
        dom.modelSelector.innerHTML = '';
        const defaultOption = document.createElement('option');
        defaultOption.value = MODEL_NAME;
        defaultOption.textContent = '默认 (使用AI Studio当前模型)';
        dom.modelSelector.appendChild(defaultOption);
        state.selectedModel = MODEL_NAME;

        const errorOption = document.createElement('option');
        errorOption.disabled = true;
        errorOption.textContent = `加载失败: ${error.message.substring(0, 50)}`;
        dom.modelSelector.appendChild(errorOption);
        updateControlsForSelectedModel(addLogEntry);
    } finally {
        dom.modelSelector.disabled = false;
        dom.refreshModelsButton.disabled = false;
    }
}

/**
 * Update model parameter controls based on selected model
 * Sets temperature, max tokens, top-p sliders to model-specific defaults
 * @param {Function} addLogEntry - Log function to report status
 */
export function updateControlsForSelectedModel(addLogEntry) {
    const selectedModelData = state.allModelsData.find(m => m.id === state.selectedModel);

    const GLOBAL_DEFAULT_TEMP = 1.0;
    const GLOBAL_DEFAULT_MAX_TOKENS = 2048;
    const GLOBAL_MAX_SUPPORTED_MAX_TOKENS = 8192;
    const GLOBAL_DEFAULT_TOP_P = 0.95;

    let temp = GLOBAL_DEFAULT_TEMP;
    let maxTokens = GLOBAL_DEFAULT_MAX_TOKENS;
    let supportedMaxTokens = GLOBAL_MAX_SUPPORTED_MAX_TOKENS;
    let topP = GLOBAL_DEFAULT_TOP_P;

    if (selectedModelData) {
        temp = (selectedModelData.default_temperature !== undefined && selectedModelData.default_temperature !== null)
            ? selectedModelData.default_temperature
            : GLOBAL_DEFAULT_TEMP;

        if (selectedModelData.default_max_output_tokens !== undefined && selectedModelData.default_max_output_tokens !== null) {
            maxTokens = selectedModelData.default_max_output_tokens;
        }
        if (selectedModelData.supported_max_output_tokens !== undefined && selectedModelData.supported_max_output_tokens !== null) {
            supportedMaxTokens = selectedModelData.supported_max_output_tokens;
        } else if (maxTokens > GLOBAL_MAX_SUPPORTED_MAX_TOKENS) {
            supportedMaxTokens = maxTokens;
        }
        // Ensure maxTokens does not exceed its own supportedMaxTokens for initial value
        if (maxTokens > supportedMaxTokens) maxTokens = supportedMaxTokens;

        topP = (selectedModelData.default_top_p !== undefined && selectedModelData.default_top_p !== null)
            ? selectedModelData.default_top_p
            : GLOBAL_DEFAULT_TOP_P;

        if (addLogEntry) {
            addLogEntry(`[信息] 为模型 '${state.selectedModel}' 应用参数: Temp=${temp}, MaxTokens=${maxTokens} (滑块上限 ${supportedMaxTokens}), TopP=${topP}`);
        }
    } else if (state.selectedModel === MODEL_NAME) {
        if (addLogEntry) {
            addLogEntry(`[信息] 使用代理模型 '${MODEL_NAME}'，应用全局默认参数。`);
        }
    } else {
        if (addLogEntry) {
            addLogEntry(`[警告] 未找到模型 '${state.selectedModel}' 的数据，应用全局默认参数。`);
        }
    }

    // Update temperature controls
    if (dom.temperatureSlider) {
        dom.temperatureSlider.min = "0";
        dom.temperatureSlider.max = "2";
        dom.temperatureSlider.step = "0.01";
        dom.temperatureSlider.value = temp;
    }
    if (dom.temperatureValue) {
        dom.temperatureValue.min = "0";
        dom.temperatureValue.max = "2";
        dom.temperatureValue.step = "0.01";
        dom.temperatureValue.value = temp;
    }

    // Update max tokens controls
    if (dom.maxOutputTokensSlider) {
        dom.maxOutputTokensSlider.min = "1";
        dom.maxOutputTokensSlider.max = supportedMaxTokens;
        dom.maxOutputTokensSlider.step = "1";
        dom.maxOutputTokensSlider.value = maxTokens;
    }
    if (dom.maxOutputTokensValue) {
        dom.maxOutputTokensValue.min = "1";
        dom.maxOutputTokensValue.max = supportedMaxTokens;
        dom.maxOutputTokensValue.step = "1";
        dom.maxOutputTokensValue.value = maxTokens;
    }

    // Update top-p controls
    if (dom.topPSlider) {
        dom.topPSlider.min = "0";
        dom.topPSlider.max = "1";
        dom.topPSlider.step = "0.01";
        dom.topPSlider.value = topP;
    }
    if (dom.topPValue) {
        dom.topPValue.min = "0";
        dom.topPValue.max = "1";
        dom.topPValue.step = "0.01";
        dom.topPValue.value = topP;
    }

    // Update state
    state.modelSettings.temperature = parseFloat(temp);
    state.modelSettings.maxOutputTokens = parseInt(maxTokens);
    state.modelSettings.topP = parseFloat(topP);

    // Update thinking budget maximum
    updateThinkingBudgetMax(state.selectedModel);

    // Update thinking controls visibility based on model and thinking mode state
    updateThinkingControlsVisibility();
}

/**
 * Bind model selector event listeners
 * @param {Function} addLogEntry - Log function to report status
 */
export function bindModelSelectorEvents(addLogEntry) {
    if (dom.modelSelector) {
        dom.modelSelector.addEventListener('change', (e) => {
            state.selectedModel = e.target.value;
            setLocalStorage(SELECTED_MODEL_KEY, state.selectedModel);
            updateControlsForSelectedModel(addLogEntry);
            if (addLogEntry) {
                addLogEntry(`[信息] 已切换到模型: ${state.selectedModel}`);
            }
        });
    }

    if (dom.refreshModelsButton) {
        dom.refreshModelsButton.addEventListener('click', () => {
            loadModelList(addLogEntry);
        });
    }
}
