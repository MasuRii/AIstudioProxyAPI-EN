/**
 * DOM Element References
 * Centralized DOM element management
 */

export const dom = {
    // Chat elements
    chatbox: null,
    userInput: null,
    sendButton: null,
    clearButton: null,

    // Sidebar elements
    sidebarPanel: null,
    toggleSidebarButton: null,
    leftSettingsSidebar: null,
    toggleLeftSidebarButton: null,

    // Log elements
    logTerminal: null,
    logStatusElement: null,
    clearLogButton: null,

    // Model selector
    modelSelector: null,
    refreshModelsButton: null,

    // Views
    chatView: null,
    serverInfoView: null,
    modelSettingsView: null,

    // Navigation
    navChatButton: null,
    navServerInfoButton: null,
    navModelSettingsButton: null,

    // API Info
    apiInfoContent: null,
    healthStatusDisplay: null,
    refreshServerInfoButton: null,

    // Theme
    themeToggleButton: null,
    htmlRoot: null,

    // Model Settings
    systemPromptInput: null,
    temperatureSlider: null,
    temperatureValue: null,
    maxOutputTokensSlider: null,
    maxOutputTokensValue: null,
    topPSlider: null,
    topPValue: null,
    stopSequencesInput: null,
    saveModelSettingsButton: null,
    resetModelSettingsButton: null,
    settingsStatusElement: null,

    // Thinking Mode Controls
    enableThinkingToggle: null,
    thinkingLevelSelector: null,
    enableManualBudgetToggle: null,
    thinkingBudgetSlider: null,
    thinkingBudgetValue: null,
    thinkingBudgetControlsContainer: null,
    thinkingModeGroup: null,
    thinkingLevelGroup: null,
    manualBudgetGroup: null,
    thinkingBudgetGroup: null,

    // Tools
    enableGoogleSearchToggle: null,

    // API Key Management
    apiKeyStatus: null,
    newApiKeyInput: null,
    toggleApiKeyVisibilityButton: null,
    testApiKeyButton: null,
    apiKeyList: null
};

/**
 * Initialize all DOM element references
 * Call this once on DOMContentLoaded
 */
export function initializeDOMReferences() {
    // Chat elements
    dom.chatbox = document.getElementById('chatbox');
    dom.userInput = document.getElementById('userInput');
    dom.sendButton = document.getElementById('sendButton');
    dom.clearButton = document.getElementById('clearButton');

    // Sidebar elements
    dom.sidebarPanel = document.getElementById('sidebarPanel');
    dom.toggleSidebarButton = document.getElementById('toggleSidebarButton');
    dom.leftSettingsSidebar = document.getElementById('leftSettingsSidebar');
    dom.toggleLeftSidebarButton = document.getElementById('toggleLeftSidebarButton');

    // Log elements
    dom.logTerminal = document.getElementById('log-terminal');
    dom.logStatusElement = document.getElementById('log-status');
    dom.clearLogButton = document.getElementById('clearLogButton');

    // Model selector
    dom.modelSelector = document.getElementById('modelSelector');
    dom.refreshModelsButton = document.getElementById('refreshModelsButton');

    // Views
    dom.chatView = document.getElementById('chat-view');
    dom.serverInfoView = document.getElementById('server-info-view');
    dom.modelSettingsView = document.getElementById('model-settings-view');

    // Navigation
    dom.navChatButton = document.getElementById('nav-chat');
    dom.navServerInfoButton = document.getElementById('nav-server-info');
    dom.navModelSettingsButton = document.getElementById('nav-model-settings');

    // API Info
    dom.apiInfoContent = document.getElementById('api-info-content');
    dom.healthStatusDisplay = document.getElementById('health-status-display');
    dom.refreshServerInfoButton = document.getElementById('refreshServerInfoButton');

    // Theme
    dom.themeToggleButton = document.getElementById('themeToggleButton');
    dom.htmlRoot = document.documentElement;

    // Model Settings
    dom.systemPromptInput = document.getElementById('systemPrompt');
    dom.temperatureSlider = document.getElementById('temperatureSlider');
    dom.temperatureValue = document.getElementById('temperatureValue');
    dom.maxOutputTokensSlider = document.getElementById('maxOutputTokensSlider');
    dom.maxOutputTokensValue = document.getElementById('maxOutputTokensValue');
    dom.topPSlider = document.getElementById('topPSlider');
    dom.topPValue = document.getElementById('topPValue');
    dom.stopSequencesInput = document.getElementById('stopSequences');
    dom.saveModelSettingsButton = document.getElementById('saveModelSettingsButton');
    dom.resetModelSettingsButton = document.getElementById('resetModelSettingsButton');
    dom.settingsStatusElement = document.getElementById('settings-status');

    // Thinking Mode Controls
    dom.enableThinkingToggle = document.getElementById('enableThinkingToggle');
    dom.thinkingLevelSelector = document.getElementById('thinkingLevelSelector');
    dom.enableManualBudgetToggle = document.getElementById('enableManualBudgetToggle');
    dom.thinkingBudgetSlider = document.getElementById('thinkingBudgetSlider');
    dom.thinkingBudgetValue = document.getElementById('thinkingBudgetValue');
    dom.thinkingBudgetControlsContainer = document.getElementById('thinkingBudgetControlsContainer');
    dom.thinkingModeGroup = document.getElementById('thinkingModeGroup');
    dom.thinkingLevelGroup = document.getElementById('thinkingLevelGroup');
    dom.manualBudgetGroup = document.getElementById('manualBudgetGroup');
    dom.thinkingBudgetGroup = document.getElementById('thinkingBudgetGroup');

    // Tools
    dom.enableGoogleSearchToggle = document.getElementById('enableGoogleSearchToggle');

    // API Key Management
    dom.apiKeyStatus = document.getElementById('apiKeyStatus');
    dom.newApiKeyInput = document.getElementById('newApiKey');
    dom.toggleApiKeyVisibilityButton = document.getElementById('toggleApiKeyVisibility');
    dom.testApiKeyButton = document.getElementById('testApiKeyButton');
    dom.apiKeyList = document.getElementById('apiKeyList');
}
