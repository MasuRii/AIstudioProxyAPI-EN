/**
 * Thinking Mode Controls
 * Handles thinking mode, budget controls, and reasoning effort for Gemini models
 */

import { dom } from '../dom.js';
import { state } from '../state.js';

/**
 * Check if model uses thinking level (Gemini 3 Pro)
 * @param {string} modelId - Model identifier
 * @returns {boolean} True if model uses thinking level
 */
export function modelUsesThinkingLevel(modelId) {
    try {
        const id = String(modelId || '').toLowerCase();
        return id.includes('gemini-3') && id.includes('pro');
    } catch (e) {
        return false;
    }
}

/**
 * Compute reasoning effort parameter based on model and settings
 * @param {Object} settings - Model settings object
 * @returns {string|number} Reasoning effort value (0, 'none', 'low', 'high', or number)
 */
export function computeReasoningEffort(settings) {
    try {
        const useLevels = modelUsesThinkingLevel(state.selectedModel);
        const id = String(state.selectedModel || '').toLowerCase();
        const hasMainToggle = id.includes('flash');

        // Gemini 3 Pro: uses level system
        if (useLevels) {
            if (!settings.enableThinking) return 0;
            const lvl = (settings.thinkingLevel || '').toLowerCase();
            if (lvl === 'low' || lvl === 'high') return lvl;
            return 'low';
        }

        // Flash models: have main thinking toggle
        if (hasMainToggle) {
            if (!settings.enableThinking) return 0;
            if (settings.enableManualBudget) {
                const budget = parseInt(settings.thinkingBudget);
                if (!isNaN(budget) && budget > 0) return budget;
            }
            return 'none';
        }

        // Other models: budget-based
        if (settings.enableManualBudget) {
            const budget = parseInt(settings.thinkingBudget);
            if (!isNaN(budget) && budget > 0) return budget;
            return 8192;
        }
        return 'none';
    } catch (e) {
        return 'none';
    }
}

/**
 * Update visibility of thinking controls based on model type and settings
 * Handles different UI states for different model types:
 * - Gemini 3 Pro: Only show level selector
 * - Gemini 2.5 Pro: Hide main toggle, show budget controls
 * - Flash models: Show all controls, hide budget when thinking is OFF
 * - Other models: Show budget controls
 */
export function updateThinkingControlsVisibility() {
    try {
        const id = String(state.selectedModel || '').toLowerCase();
        const isGemini3Pro = id.includes('gemini-3') && id.includes('pro');
        const isGemini25Pro = id.includes('gemini-2.5-pro');
        const isFlash = id.includes('flash');

        // Read from BOTH sources to ensure we have the latest value
        // Checkbox state takes precedence if the element exists
        const checkboxState = dom.enableThinkingToggle ? dom.enableThinkingToggle.checked : null;
        const settingsState = state.modelSettings.enableThinking;
        const thinkingEnabled = checkboxState !== null ? !!checkboxState : !!settingsState;

        // Gemini 3 Pro: always hide main toggle and budget controls, show level selector
        if (isGemini3Pro) {
            if (dom.thinkingModeGroup) dom.thinkingModeGroup.style.display = 'none';
            if (dom.thinkingLevelGroup) dom.thinkingLevelGroup.style.display = '';
            if (dom.manualBudgetGroup) dom.manualBudgetGroup.style.display = 'none';
            if (dom.thinkingBudgetGroup) dom.thinkingBudgetGroup.style.display = 'none';
            return;
        }

        // Gemini 2.5 Pro: hide main thinking toggle
        if (isGemini25Pro) {
            if (dom.thinkingModeGroup) dom.thinkingModeGroup.style.display = 'none';
        } else {
            if (dom.thinkingModeGroup) dom.thinkingModeGroup.style.display = '';
        }

        // Always hide level selector for non-Gemini 3 Pro models
        if (dom.thinkingLevelGroup) dom.thinkingLevelGroup.style.display = 'none';

        // Flash/Flash Lite models: hide budget controls when thinking mode is OFF
        // Using CSS class with !important for robust hiding
        if (isFlash) {
            if (thinkingEnabled) {
                if (dom.manualBudgetGroup) {
                    dom.manualBudgetGroup.classList.remove('thinking-controls-hidden');
                    dom.manualBudgetGroup.style.display = '';
                }
                if (dom.thinkingBudgetGroup) {
                    dom.thinkingBudgetGroup.classList.remove('thinking-controls-hidden');
                    dom.thinkingBudgetGroup.style.display = '';
                }
            } else {
                if (dom.manualBudgetGroup) {
                    dom.manualBudgetGroup.classList.add('thinking-controls-hidden');
                    dom.manualBudgetGroup.style.display = 'none';
                }
                if (dom.thinkingBudgetGroup) {
                    dom.thinkingBudgetGroup.classList.add('thinking-controls-hidden');
                    dom.thinkingBudgetGroup.style.display = 'none';
                }
            }
        } else {
            // Non-flash models: always show budget controls
            if (dom.manualBudgetGroup) {
                dom.manualBudgetGroup.classList.remove('thinking-controls-hidden');
                dom.manualBudgetGroup.style.display = '';
            }
            if (dom.thinkingBudgetGroup) {
                dom.thinkingBudgetGroup.classList.remove('thinking-controls-hidden');
                dom.thinkingBudgetGroup.style.display = '';
            }
        }

        // Update thinking budget controls container visibility
        if (dom.thinkingBudgetControlsContainer) {
            const shouldShowControls = !!(dom.enableManualBudgetToggle && dom.enableManualBudgetToggle.checked);
            dom.thinkingBudgetControlsContainer.style.display = shouldShowControls ? 'flex' : 'none';
        }
    } catch (e) {
        console.error('Error updating thinking controls visibility:', e);
    }
}

/**
 * Update thinking budget slider maximum based on model type
 * @param {string} modelId - Model identifier
 */
export function updateThinkingBudgetMax(modelId) {
    try {
        const id = String(modelId || '').toLowerCase();
        let budgetMax = 32768;

        if (id.includes('flash-lite')) {
            budgetMax = 24576;
        } else if (id.includes('flash')) {
            budgetMax = 24576;
        } else if (id.includes('gemini-2.5-pro')) {
            budgetMax = 32768;
        }

        if (dom.thinkingBudgetSlider) dom.thinkingBudgetSlider.max = String(budgetMax);
        if (dom.thinkingBudgetValue) dom.thinkingBudgetValue.max = String(budgetMax);
    } catch (e) {
        // Silently ignore errors
    }
}

/**
 * Bind thinking mode event listeners
 */
export function bindThinkingModeEvents() {
    // Thinking toggle
    if (dom.enableThinkingToggle) {
        dom.enableThinkingToggle.addEventListener('change', () => {
            state.modelSettings.enableThinking = !!dom.enableThinkingToggle.checked;
            updateThinkingControlsVisibility();
        });
    }

    // Manual budget toggle
    if (dom.enableManualBudgetToggle) {
        dom.enableManualBudgetToggle.addEventListener('change', () => {
            state.modelSettings.enableManualBudget = !!dom.enableManualBudgetToggle.checked;
            updateThinkingControlsVisibility();
        });
    }

    // Thinking budget slider
    if (dom.thinkingBudgetSlider && dom.thinkingBudgetValue) {
        dom.thinkingBudgetSlider.addEventListener('input', (e) => {
            dom.thinkingBudgetValue.value = e.target.value;
            state.modelSettings.thinkingBudget = parseInt(e.target.value);
        });
        dom.thinkingBudgetValue.addEventListener('input', (e) => {
            dom.thinkingBudgetSlider.value = e.target.value;
            state.modelSettings.thinkingBudget = parseInt(e.target.value);
        });
    }

    // Thinking level selector
    if (dom.thinkingLevelSelector) {
        dom.thinkingLevelSelector.addEventListener('change', (e) => {
            state.modelSettings.thinkingLevel = e.target.value.toLowerCase();
        });
    }
}
