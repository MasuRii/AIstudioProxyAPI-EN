/**
 * API Info Management
 * Handles fetching and displaying API information and health status
 */

import { dom } from '../dom.js';

/**
 * Format display key (convert snake_case to Title Case)
 * @param {string} key_string - Key to format
 * @returns {string} Formatted key
 */
export function formatDisplayKey(key_string) {
    return key_string
        .replace(/_/g, ' ')
        .replace(/\b\w/g, char => char.toUpperCase());
}

/**
 * Display health data recursively
 * @param {HTMLElement} targetElement - Element to display data in
 * @param {Object} data - Data to display
 * @param {string} sectionTitle - Optional section title
 */
export function displayHealthData(targetElement, data, sectionTitle) {
    if (!targetElement) {
        console.error("Target element for displayHealthData not found. Section: ", sectionTitle || 'Root');
        return;
    }

    try {
        // Clear previous content only if it's the root call
        if (!sectionTitle) {
            targetElement.innerHTML = '';
        }

        const container = document.createElement('div');
        if (sectionTitle) {
            const titleElement = document.createElement('h4');
            titleElement.textContent = sectionTitle;
            titleElement.className = 'health-section-title';
            container.appendChild(titleElement);
        }

        const ul = document.createElement('ul');
        ul.className = 'info-list health-info-list';

        for (const key in data) {
            if (Object.prototype.hasOwnProperty.call(data, key)) {
                const li = document.createElement('li');
                const strong = document.createElement('strong');
                const currentDisplayKey = formatDisplayKey(key);
                strong.textContent = `${currentDisplayKey}: `;
                li.appendChild(strong);

                const value = data[key];

                // Check for plain objects to recurse
                if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
                    const nestedContainer = document.createElement('div');
                    nestedContainer.className = 'nested-health-data';
                    li.appendChild(nestedContainer);
                    displayHealthData(nestedContainer, value, currentDisplayKey);
                } else if (typeof value === 'boolean') {
                    li.appendChild(document.createTextNode(value ? '是' : '否'));
                } else {
                    const valueSpan = document.createElement('span');
                    valueSpan.innerHTML = (value === null || value === undefined) ? 'N/A' : String(value);
                    li.appendChild(valueSpan);
                }
                ul.appendChild(li);
            }
        }
        container.appendChild(ul);
        targetElement.appendChild(container);
    } catch (error) {
        console.error(`Error within displayHealthData (processing section: ${sectionTitle || 'Root level'}):`, error);
        try {
            targetElement.innerHTML = `<p class="error-message" style="color: var(--error-color, red);">Error displaying this section (${sectionTitle || 'details'}). Check console for more info.</p>`;
        } catch (eDisplay) {
            console.error("Further error trying to display error message in targetElement:", eDisplay);
        }
    }
}

/**
 * Load and display API information
 * @param {Function} addLogEntry - Log function to report status
 * @returns {Promise<void>}
 */
export async function loadApiInfo(addLogEntry) {
    if (!dom.apiInfoContent) return;

    dom.apiInfoContent.innerHTML = '<div class="loading-indicator"><div class="loading-spinner"></div><span>正在加载 API 信息...</span></div>';

    try {
        console.log("[loadApiInfo] Attempting to fetch /api/info...");
        const response = await fetch('/api/info');
        console.log("[loadApiInfo] Fetch response received. Status:", response.status);

        if (!response.ok) {
            const errorText = `HTTP error! status: ${response.status}, statusText: ${response.statusText}`;
            console.error("[loadApiInfo] Fetch not OK. Error Details:", errorText);
            throw new Error(errorText);
        }

        const data = await response.json();
        console.log("[loadApiInfo] JSON data parsed:", data);

        const formattedData = {
            'API Base URL': data.api_base_url ? `<code>${data.api_base_url}</code>` : '未知',
            'Server Base URL': data.server_base_url ? `<code>${data.server_base_url}</code>` : '未知',
            'Model Name': data.model_name ? `<code>${data.model_name}</code>` : '未知',
            'API Key Required': data.api_key_required
                ? '<span style="color: orange;">⚠️ 是 (请在后端配置)</span>'
                : '<span style="color: green;">✅ 否</span>',
            'Message': data.message || '无'
        };

        displayHealthData(dom.apiInfoContent, formattedData);

        console.log("[loadApiInfo] displayHealthData call succeeded.");
    } catch (error) {
        console.error("[loadApiInfo] Error:", error);
        if (error && error.stack) {
            console.error("[loadApiInfo] Stack trace:", error.stack);
        }
        dom.apiInfoContent.innerHTML = `<div class="info-list"><div><strong style="color: var(--error-msg-text);">错误:</strong> <span style="color: var(--error-msg-text);">加载 API 信息失败: ${error.message} (详情请查看控制台)</span></div></div>`;
    }
}

/**
 * Fetch and display health status
 * @param {Function} addLogEntry - Log function to report status
 * @returns {Promise<void>}
 */
export async function fetchHealthStatus(addLogEntry) {
    if (!dom.healthStatusDisplay) {
        console.error("healthStatusDisplay element not found for fetchHealthStatus");
        if (addLogEntry) {
            addLogEntry("[错误] Health status display element not found.");
        }
        return;
    }

    dom.healthStatusDisplay.innerHTML = '<p class="loading-indicator">正在加载健康状态...</p>';

    try {
        const response = await fetch('/health');
        if (!response.ok) {
            let errorText = `HTTP error! Status: ${response.status}`;
            try {
                const errorData = await response.json();
                if (errorData && errorData.message) {
                    errorText = errorData.message;
                } else if (errorData && errorData.details && typeof errorData.details === 'string') {
                    errorText = errorData.details;
                } else if (errorData && errorData.detail && typeof errorData.detail === 'string') {
                    errorText = errorData.detail;
                }
            } catch (e) {
                console.warn("Failed to parse error response body from /health:", e);
            }
            throw new Error(errorText);
        }

        const data = await response.json();
        displayHealthData(dom.healthStatusDisplay, data);

        if (addLogEntry) {
            addLogEntry("[信息] 健康状态已成功加载并显示。");
        }
    } catch (error) {
        console.error('获取健康状态失败:', error);
        dom.healthStatusDisplay.innerHTML = `<p class="error-message">获取健康状态失败: ${error.message}</p>`;
        if (addLogEntry) {
            addLogEntry(`[错误] 获取健康状态失败: ${error.message}`);
        }
    }
}

/**
 * Bind API info refresh events
 * @param {Function} addLogEntry - Log function to report status
 */
export function bindApiInfoEvents(addLogEntry) {
    if (dom.refreshServerInfoButton) {
        dom.refreshServerInfoButton.addEventListener('click', () => {
            loadApiInfo(addLogEntry);
            fetchHealthStatus(addLogEntry);
        });
    }
}
