import { MODEL_NAME, DEFAULT_SYSTEM_PROMPT } from './constants.js';

// Application State
export const state = {
    selectedModel: MODEL_NAME,
    allModelsData: [],
    conversationHistory: [],
    logWebSocket: null,
    logHistory: [],

    modelSettings: {
        systemPrompt: DEFAULT_SYSTEM_PROMPT,
        temperature: -1,
        maxOutputTokens: -1,
        topP: -1,
        stopSequences: "",
        enableThinking: false,
        enableManualBudget: false,
        thinkingBudget: 8192,
        thinkingLevel: "",
        enableGoogleSearch: false
    }
};
