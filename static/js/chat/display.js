/**
 * Chat Message Display
 * Handles rendering and formatting of chat messages
 */

import { dom } from '../dom.js';

/**
 * Display a message in the chatbox
 * @param {string} text - Message text to display
 * @param {string} role - Message role (user, assistant, system, error)
 * @param {number} index - Message index in conversation history
 * @returns {HTMLElement} The created message element
 */
export function displayMessage(text, role, index) {
    const messageElement = document.createElement('div');
    messageElement.classList.add('message', `${role}-message`);

    if (index !== undefined && (role === 'user' || role === 'assistant' || role === 'system')) {
        messageElement.dataset.index = index;
    }

    const messageContentElement = document.createElement('div');
    messageContentElement.classList.add('message-content');
    renderMessageContent(messageContentElement, text || (role === 'assistant' ? '' : text)); // Allow empty initial for streaming

    messageElement.appendChild(messageContentElement);
    dom.chatbox.appendChild(messageElement);

    // Ensure scroll happens after render
    setTimeout(() => {
        if (dom.chatbox.lastChild === messageElement) {
            dom.chatbox.scrollTop = dom.chatbox.scrollHeight;
        }
    }, 0);

    return messageElement;
}

/**
 * Render message content with markdown-like formatting
 * Supports: code blocks, inline code, bold, italic, links
 * @param {HTMLElement} element - Target element to render content into
 * @param {string} text - Text to render
 */
export function renderMessageContent(element, text) {
    if (text == null) {
        element.innerHTML = '';
        return;
    }

    // HTML escape function
    const escapeHtml = (unsafe) =>
        unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");

    let safeText = escapeHtml(String(text));

    // Code blocks (triple backticks)
    safeText = safeText.replace(
        /```(?:[\w-]*\n)?([\s\S]+?)\n?```/g,
        (match, code) => `<pre><code>${code.trim()}</code></pre>`
    );

    // Inline code (single backticks)
    safeText = safeText.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Links - preserve for later replacement
    const links = [];
    safeText = safeText.replace(
        /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
        (match, linkText, url) => {
            links.push({ text: linkText, url: url });
            return `__LINK_${links.length - 1}__`;
        }
    );

    // Bold (** or __)
    safeText = safeText.replace(
        /(\*\*|__)(?=\S)([\s\S]*?\S)\1/g,
        '<strong>$2</strong>'
    );

    // Italic (* or _)
    safeText = safeText.replace(
        /(\*|_)(?=\S)([\s\S]*?\S)\1/g,
        '<em>$2</em>'
    );

    // Replace link placeholders
    safeText = safeText.replace(/__LINK_(\d+)__/g, (match, index) => {
        const link = links[parseInt(index)];
        return `<a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">${link.text}</a>`;
    });

    element.innerHTML = safeText;

    // Apply syntax highlighting if highlight.js is available
    if (typeof hljs !== 'undefined' && element.querySelectorAll('pre code').length > 0) {
        element.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
    }
}

/**
 * Clear all messages from chatbox
 */
export function clearChatDisplay() {
    if (dom.chatbox) {
        dom.chatbox.innerHTML = '';
    }
}

/**
 * Scroll chatbox to bottom
 */
export function scrollChatToBottom() {
    if (dom.chatbox) {
        dom.chatbox.scrollTop = dom.chatbox.scrollHeight;
    }
}

/**
 * Check if chatbox is scrolled to bottom (within threshold)
 * @param {number} threshold - Pixels from bottom to consider "at bottom"
 * @returns {boolean}
 */
export function isChatScrolledToBottom(threshold = 25) {
    if (!dom.chatbox) return false;
    return dom.chatbox.scrollHeight - dom.chatbox.clientHeight <= dom.chatbox.scrollTop + threshold;
}
