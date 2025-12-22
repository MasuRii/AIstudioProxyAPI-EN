# Streaming Modes Explained

This document details the three-layer streaming response acquisition mechanism of the AI Studio Proxy API, as well as the request queue and concurrency processing logic.

## 🔄 Three-Layer Response Acquisition Mechanism Overview

The project implements a three-layer response acquisition mechanism to ensure high availability and optimal performance:

```
Request → Layer 1: Integrated Streaming Proxy (True Streaming) → Layer 2: External Helper Service → Layer 3: Playwright Page Interaction (Pseudo-Streaming)
```

### How It Works

1. **Priority Processing**: Attempt to acquire response in order of layers.
2. **Auto Downgrade**: Automatically downgrade to lower layer if upper layer fails.
3. **Performance Optimization**: Prioritize high-performance solutions.
4. **Full Fallback**: Ensure response acquisition in any situation.

## 🚀 Layer 1: Integrated Streaming Proxy (Standard Streaming)

### Overview

The integrated streaming proxy is the default enabled high-performance response acquisition solution, providing **True Streaming**.

### Technical Features

- **Independent Process**: Runs in an independent process, does not affect the main service.
- **Direct Forwarding**: Directly forwards requests to AI Studio, reducing intermediate steps.
- **Real-time Transmission**: Natively supports SSE (Server-Sent Events), tokens are generated and transmitted in real-time.
- **High Performance**: Minimizes TTFT (Time To First Token), maximizes throughput.

### Configuration

#### .env File Configuration (Recommended)

```env
# Enable integrated streaming proxy
STREAM_PORT=3120

# Disable integrated streaming proxy
STREAM_PORT=0
```

### Applicable Scenarios

- **Daily Use**: Provides best performance experience.
- **Production Environment**: Stable and reliable production deployment.
- **Streaming Applications**: Applications requiring real-time response.

## 🔧 Layer 2: External Helper Service

### Overview

External Helper Service is an optional backup solution, enabled when the integrated streaming proxy is unavailable.

### Technical Features

- **External Service**: Independently deployed external service.
- **Auth Dependency**: Requires valid auth file.
- **Backup Solution**: Acts as a backup for the streaming proxy.

### Configuration

```env
# Configure Helper service endpoint
GUI_DEFAULT_HELPER_ENDPOINT=http://your-helper-service:port
```

## 🎭 Layer 3: Playwright Page Interaction (Pseudo-Streaming)

### Overview

Playwright Page Interaction is the final fallback solution. When streaming proxy is unavailable, the system controls the browser to generate the full response on the page, then simulates streaming effect to return to the client.

### "Pseudo-Streaming" Mechanism

In this mode, the response is **not** transmitted in real-time:

1. System waits for AI Studio webpage to fully generate the reply.
2. Acquires the complete text content.
3. Cuts the complete content into character blocks and quickly simulates SSE events to send to the client.

**Note**: This means the client will perceive a higher "Time To First Token" because it must wait for the entire reply to be generated before receiving data.

### Technical Features

- **Browser Automation**: Uses Camoufox browser to simulate user operations.
- **Full Parameter Support**: Supports all AI Studio parameters (`temperature`, `top_p`, etc.).
- **Final Fallback**: Ensures functionality in any situation.

### Applicable Scenarios

- **Debug Mode**: Used during development and debugging.
- **Precise Parameter Control**: Requires precise control of all parameters.
- **Troubleshooting**: Final solution when all other methods fail.

## 🚦 Request Queue and Concurrency Control

To ensure the stability of browser automation operations, the system adopts a strict serial processing mechanism.

### 1. Serial Request Queue

Since the browser page (Page Instance) is a singleton and DOM operations have state dependencies, all requests (streaming or not) enter a global FIFO queue.

- **Mechanism**: `api_utils/queue_worker.py` maintains a `request_queue`.
- **Lock**: Uses `processing_lock` to ensure only one request operates the browser or sends data via proxy at a time.

### 2. Smart Delay Mechanism

To prevent triggering AI Studio's risk control or causing browser state abnormalities when sending consecutive rapid streaming requests, the system implements a smart delay mechanism.

- **Logic**:
  - If the previous request was a streaming request, and the current request is also a streaming request.
  - And the interval between the two requests is less than 1 second.
  - The system automatically inserts a `0.5s - 1.0s` delay.
- **Purpose**: Simulate human operation rhythm, improve continuous conversation stability.

### 3. Resource Cleanup and Lock Release

- **Auto Cleanup**: After each request is processed, the Worker automatically cleans up the streaming queue and chat history (if needed).
- **Timeout Protection**: Combined with internal timeout mechanism to prevent deadlocks from blocking the queue.

## ⚙️ Mode Selection Recommendations

| Mode | Type | Latency (TTFT) | Throughput | Stability | Applicable Scenario |
| --- | --- | --- | --- | --- | --- |
| **Integrated Streaming Proxy** | True Streaming | Lowest | Highest | Highest | **Production (Recommended)** |
| **Helper Service** | Depends on impl | Medium | Medium | Medium | Special Network Environment |
| **Playwright** | Pseudo-Streaming | Highest (Wait for generation) | Lowest | Medium | Debugging, Parameter Testing |

### Troubleshooting

#### Why does streaming response feel delayed?

- **Check Mode**: Confirm if downgraded to Playwright mode (Pseudo-Streaming). If so, this is normal as it waits for full generation.
- **Check Queue**: If there are multiple concurrent requests, subsequent requests must wait for preceding ones to complete.
- **Smart Delay**: When sending consecutive requests, the system may automatically introduce a short delay.
