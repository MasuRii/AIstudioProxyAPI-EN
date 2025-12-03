/**
 * Theme Management
 * Handles light/dark mode switching
 */

import { dom } from '../dom.js';
import { THEME_KEY } from '../constants.js';
import { setLocalStorage, getLocalStorage } from '../helpers.js';

/**
 * Apply a theme (light or dark)
 * @param {string} theme - Theme to apply ('light' or 'dark')
 */
export function applyTheme(theme) {
    if (!dom.htmlRoot) return;

    if (theme === 'dark') {
        dom.htmlRoot.classList.add('dark-mode');
        if (dom.themeToggleButton) {
            dom.themeToggleButton.title = '切换到亮色模式';
        }
    } else {
        dom.htmlRoot.classList.remove('dark-mode');
        if (dom.themeToggleButton) {
            dom.themeToggleButton.title = '切换到暗色模式';
        }
    }
}

/**
 * Toggle between light and dark themes
 */
export function toggleTheme() {
    if (!dom.htmlRoot) return;

    const currentTheme = dom.htmlRoot.classList.contains('dark-mode') ? 'dark' : 'light';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    applyTheme(newTheme);
    setLocalStorage(THEME_KEY, newTheme);
}

/**
 * Load and apply saved theme preference
 */
export function loadThemePreference() {
    let preferredTheme = 'light';
    const storedTheme = getLocalStorage(THEME_KEY);

    if (storedTheme === 'dark' || storedTheme === 'light') {
        preferredTheme = storedTheme;
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        preferredTheme = 'dark';
    }

    applyTheme(preferredTheme);

    // Listen for system theme changes
    const prefersDarkScheme = window.matchMedia('(prefers-color-scheme: dark)');
    prefersDarkScheme.addEventListener('change', (e) => {
        const newSystemTheme = e.matches ? 'dark' : 'light';
        applyTheme(newSystemTheme);
        setLocalStorage(THEME_KEY, newSystemTheme);
    });
}

/**
 * Bind theme toggle event
 */
export function bindThemeEvents() {
    if (dom.themeToggleButton) {
        dom.themeToggleButton.addEventListener('click', toggleTheme);
    }
}
