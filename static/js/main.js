/**
 * Main Application Entry Point
 * Orchestrates initialization of all modules
 */

// ============================================================================
// MODULE IMPORTS
// ============================================================================

// Core modules
import { initializeDOMReferences, dom } from './dom.js';
import { state } from './state.js';

// Model modules
import { loadModelList, updateControlsForSelectedModel, bindModelSelectorEvents } from './models/list.js';
import { initializeModelSettings, updateModelSettingsUI, saveModelSettings, resetModelSettings, bindModelSettingsEvents } from './models/settings.js';
import { bindThinkingModeEvents } from './models/thinking.js';

// Chat modules
import { displayMessage, renderMessageContent } from './chat/display.js';
import { initializeChatHistory, saveChatHistory, clearChatHistory } from './chat/history.js';
import { sendMessage, bindSendEvents } from './chat/send.js';

// Logs modules
import { addLogEntry, initializeLogs, bindLogEvents } from './logs/websocket.js';

// API modules
import { loadApiInfo, fetchHealthStatus, bindApiInfoEvents } from './api/info.js';

// UI modules
import { loadThemePreference, bindThemeEvents } from './ui/theme.js';
import { switchView, bindViewEvents } from './ui/views.js';
import { loadLeftSidebarState, loadRightSidebarState, checkInitialSidebarState, bindSidebarEvents } from './ui/sidebars.js';

// ============================================================================
// APPLICATION INITIALIZATION
// ============================================================================

/**
 * Initialize application when DOM is ready
 */
document.addEventListener('DOMContentLoaded', async () => {
    console.log('[Main] Application initializing...');

    try {
        // Step 1: Initialize DOM references
        console.log('[Main] Step 1: Initializing DOM references...');
        initializeDOMReferences();

        // Step 2: Load theme preference
        console.log('[Main] Step 2: Loading theme preference...');
        loadThemePreference();

        // Step 3: Load sidebar states
        console.log('[Main] Step 3: Loading sidebar states...');
        loadLeftSidebarState();
        loadRightSidebarState();
        checkInitialSidebarState();

        // Step 4: Initialize model settings
        console.log('[Main] Step 4: Initializing model settings...');
        initializeModelSettings(addLogEntry);

        // Step 5: Load model list
        console.log('[Main] Step 5: Loading model list...');
        await loadModelList(addLogEntry);

        // Step 6: Initialize chat history
        console.log('[Main] Step 6: Initializing chat history...');
        initializeChatHistory(addLogEntry);

        // Step 7: Initialize logs
        console.log('[Main] Step 7: Initializing logs...');
        initializeLogs();

        // Step 8: Enable chat controls
        console.log('[Main] Step 8: Enabling chat controls...');
        if (dom.userInput) {
            dom.userInput.disabled = false;
            dom.userInput.focus();
        }
        if (dom.sendButton) dom.sendButton.disabled = false;
        if (dom.clearButton) dom.clearButton.disabled = false;

        // Step 9: Bind all event listeners
        console.log('[Main] Step 9: Binding event listeners...');
        bindAllEventListeners();

        // Step 10: Set initial view
        console.log('[Main] Step 10: Setting initial view...');
        switchView('chat', addLogEntry);

        console.log('[Main] ✓ Application initialized successfully');
        addLogEntry('[信息] 应用程序初始化完成。');
    } catch (error) {
        console.error('[Main] ✗ Initialization failed:', error);
        addLogEntry(`[错误] 应用程序初始化失败: ${error.message}`);

        // Display error to user
        if (dom.chatbox) {
            dom.chatbox.innerHTML = `
                <div style="padding: 20px; color: var(--error-color); text-align: center;">
                    <h3>初始化失败</h3>
                    <p>${error.message}</p>
                    <p>请刷新页面重试，或查看控制台获取详细信息。</p>
                </div>
            `;
        }
    }
});

// ============================================================================
// EVENT LISTENER BINDINGS
// ============================================================================

/**
 * Bind all event listeners
 */
function bindAllEventListeners() {
    // Theme
    bindThemeEvents();

    // Views
    bindViewEvents(addLogEntry);

    // Sidebars
    bindSidebarEvents();

    // Models
    bindModelSelectorEvents(addLogEntry);
    bindModelSettingsEvents(addLogEntry, saveChatHistory, renderMessageContent);
    bindThinkingModeEvents();

    // Chat
    bindSendEvents(addLogEntry);
    if (dom.clearButton) {
        dom.clearButton.addEventListener('click', () => clearChatHistory(addLogEntry));
    }

    // Logs
    bindLogEvents();

    // API
    bindApiInfoEvents(addLogEntry);

    console.log('[Main] All event listeners bound successfully');
}

// ============================================================================
// EXPORTS (for testing and module usage)
// ============================================================================

export {
    // Core
    addLogEntry,

    // Models
    loadModelList,
    updateModelSettingsUI,
    saveModelSettings,
    resetModelSettings,

    // Chat
    displayMessage,
    renderMessageContent,
    sendMessage,
    initializeChatHistory,
    saveChatHistory,
    clearChatHistory,

    // UI
    switchView,

    // API
    loadApiInfo,
    fetchHealthStatus
};
