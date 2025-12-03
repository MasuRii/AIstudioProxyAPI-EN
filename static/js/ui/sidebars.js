/**
 * Sidebar Management
 * Handles left and right sidebar toggle and state persistence
 */

import { dom } from '../dom.js';
import { setLocalStorage, getLocalStorage, isMobile } from '../helpers.js';

/**
 * Load left sidebar state from localStorage
 */
export function loadLeftSidebarState() {
    const savedState = getLocalStorage('leftSidebarCollapsed');
    const isCollapsed = savedState === 'true' || isMobile();

    if (dom.leftSettingsSidebar) {
        if (isCollapsed) {
            dom.leftSettingsSidebar.classList.add('collapsed');
        } else {
            dom.leftSettingsSidebar.classList.remove('collapsed');
        }
    }
}

/**
 * Load right sidebar state from localStorage
 */
export function loadRightSidebarState() {
    const savedState = getLocalStorage('rightSidebarCollapsed');
    const isCollapsed = savedState !== 'false'; // Default: collapsed

    if (dom.sidebarPanel) {
        if (isCollapsed) {
            dom.sidebarPanel.classList.add('collapsed');
        } else {
            dom.sidebarPanel.classList.remove('collapsed');
        }
    }
}

/**
 * Toggle left sidebar (settings)
 */
export function toggleLeftSidebar() {
    if (!dom.leftSettingsSidebar) return;

    const isCollapsed = dom.leftSettingsSidebar.classList.toggle('collapsed');
    setLocalStorage('leftSidebarCollapsed', String(isCollapsed));
}

/**
 * Toggle right sidebar (logs)
 */
export function toggleRightSidebar() {
    if (!dom.sidebarPanel) return;

    const isCollapsed = dom.sidebarPanel.classList.toggle('collapsed');
    setLocalStorage('rightSidebarCollapsed', String(isCollapsed));
}

/**
 * Check and set initial sidebar state (for mobile)
 */
export function checkInitialSidebarState() {
    if (isMobile()) {
        if (dom.sidebarPanel) dom.sidebarPanel.classList.add('collapsed');
        if (dom.leftSettingsSidebar) dom.leftSettingsSidebar.classList.add('collapsed');
    }
}

/**
 * Bind sidebar toggle events
 */
export function bindSidebarEvents() {
    if (dom.toggleLeftSidebarButton) {
        dom.toggleLeftSidebarButton.addEventListener('click', toggleLeftSidebar);
    }
    if (dom.toggleSidebarButton) {
        dom.toggleSidebarButton.addEventListener('click', toggleRightSidebar);
    }

    // Handle window resize for responsive sidebars
    window.addEventListener('resize', () => {
        if (isMobile()) {
            if (dom.sidebarPanel) dom.sidebarPanel.classList.add('collapsed');
            if (dom.leftSettingsSidebar) dom.leftSettingsSidebar.classList.add('collapsed');
        }
    });
}
