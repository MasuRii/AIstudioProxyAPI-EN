/**
 * View Switching
 * Handles switching between chat, server-info, and model-settings views
 */

import { dom } from '../dom.js';
import { updateModelSettingsUI } from '../models/settings.js';
import { loadApiInfo, fetchHealthStatus } from '../api/info.js';

/**
 * Switch to a different view
 * @param {string} viewId - View to switch to ('chat', 'server-info', 'model-settings')
 * @param {Function} addLogEntry - Log function to report status
 */
export function switchView(viewId, addLogEntry) {
    // Hide all views
    if (dom.chatView) dom.chatView.style.display = 'none';
    if (dom.serverInfoView) dom.serverInfoView.style.display = 'none';
    if (dom.modelSettingsView) dom.modelSettingsView.style.display = 'none';

    // Remove active class from all nav buttons
    if (dom.navChatButton) dom.navChatButton.classList.remove('active');
    if (dom.navServerInfoButton) dom.navServerInfoButton.classList.remove('active');
    if (dom.navModelSettingsButton) dom.navModelSettingsButton.classList.remove('active');

    // Show selected view and activate nav button
    if (viewId === 'chat') {
        if (dom.chatView) dom.chatView.style.display = 'flex';
        if (dom.navChatButton) dom.navChatButton.classList.add('active');
        if (dom.userInput) dom.userInput.focus();
    } else if (viewId === 'server-info') {
        if (dom.serverInfoView) dom.serverInfoView.style.display = 'flex';
        if (dom.navServerInfoButton) dom.navServerInfoButton.classList.add('active');
        fetchHealthStatus(addLogEntry);
        loadApiInfo(addLogEntry);
    } else if (viewId === 'model-settings') {
        if (dom.modelSettingsView) dom.modelSettingsView.style.display = 'flex';
        if (dom.navModelSettingsButton) dom.navModelSettingsButton.classList.add('active');
        updateModelSettingsUI();
    }
}

/**
 * Bind view switching events
 * @param {Function} addLogEntry - Log function to report status
 */
export function bindViewEvents(addLogEntry) {
    if (dom.navChatButton) {
        dom.navChatButton.addEventListener('click', () => switchView('chat', addLogEntry));
    }
    if (dom.navServerInfoButton) {
        dom.navServerInfoButton.addEventListener('click', () => switchView('server-info', addLogEntry));
    }
    if (dom.navModelSettingsButton) {
        dom.navModelSettingsButton.addEventListener('click', () => switchView('model-settings', addLogEntry));
    }
}
