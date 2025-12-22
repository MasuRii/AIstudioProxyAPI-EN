# Web UI Guide

This project features a rich, modern Web User Interface providing chat testing, status monitoring, API key management, and more.

## Access

Open the server's root address in your browser, defaulting to `http://127.0.0.1:2048/`.

**Port Configuration**:

- Default port: 2048
- Configuration: Set `PORT=2048` or `DEFAULT_FASTAPI_PORT=2048` in `.env` file
- Command line override: Use `--server-port` parameter
- GUI Configuration: Set directly via graphical launcher

## Main Features

### Chat Interface

- **Basic Chat**: Send messages and receive responses from AI Studio, supporting three-layer response acquisition mechanism
- **Markdown Support**: Supports Markdown formatting, code block highlighting, and math formula rendering
- **Automatic API Key Auth**: Chat requests automatically include Bearer token authentication, supports local storage
- **Smart Error Handling**: Provides specific hints for 401 auth errors, quota limits, etc.
- **Input Validation**: Prevents sending empty messages, double checks content validity
- **Streaming Response**: Supports real-time streaming output, providing ChatGPT-like typewriter effect
- **Client Disconnect Detection**: Smart detection of client connection status to optimize resource usage

### Server Info

Switch to "Server Info" tab to view:

- **API Call Info**: Base URL, Model Name, Auth Status, etc.
- **Service Health Check**: Detailed status of `/health` endpoint, including:
  - Playwright connection status
  - Browser connection status
  - Page readiness status
  - Queue worker status
  - Current queue length
- **System Status**: Status of three-layer response acquisition mechanism
- **Real-time Update**: Provides "Refresh" button to manually update information

### Secure API Key Management System

"Settings" tab provides complete key management features:

#### Tiered Permission View System

**How it works**:

- **Unverified State**: Only shows basic key input interface and hints
- **Verified State**: Shows complete key management interface, including server key list

**Verification Process**:

1. Enter a valid API key in the key input box
2. Click "Verify Key" button
3. After successful verification, the interface automatically refreshes to show full features
4. Verification state remains valid during the browser session

#### Key Management Features

**Key Verification**:

- Supports verifying validity of any API key
- Successfully verified keys are automatically saved to browser local storage
- Verification failure shows specific error message

**Key List View**:

- Displays all API keys configured on the server
- All keys are masked for display (Format: `xxxx****xxxx`)
- Shows key addition time and status info
- Provides individual key verification button

**Security Mechanism**:

- **Masked Display**: All keys are safely masked to protect sensitive info
- **Session Persistence**: Verification state only valid in current browser session
- **Local Storage**: Verified keys saved in browser local storage
- **Reset Function**: Can reset verification state anytime to re-verify keys

#### Key Input Interface

- **Auto Save**: Input box content automatically saved to browser local storage
- **Quick Action**: Supports Enter key for quick verification
- **Visibility Toggle**: Provides key visibility toggle button
- **Status Indication**: Real-time display of current verification state and key configuration status

### Model Settings

"Model Settings" tab allows users to configure and save (to browser local storage) the following parameters:

- **System Prompt**: Customize model behavior and role
- **Temperature**: Control randomness of generated text
- **Max Output Tokens**: Limit length of single model response
- **Top-P**: Control probability threshold for nucleus sampling
- **Thinking Mode**:
  - **Thinking Level**: For supported models (e.g., Gemini 3 Pro), choose Low or High
  - **Thinking Budget**: Manually limit Token budget for thinking process
- **Tools**:
  - **Google Search**: Enable search as a tool to improve factuality (Grounding with Google Search)
- **Stop Sequences**: Specify one or more sequences that stop model generation
- Provides "Save Settings" and "Reset to Defaults" buttons

### Model Selector

Select desired model in main chat interface; selection attempts to switch model in AI Studio backend.

### System Logs

Right sidebar (expandable/collapsible) displays real-time backend logs via WebSocket (`/ws/logs`):

- Includes log level, timestamp, and message content
- Provides clear log button
- Used for debugging and monitoring

### Theme Toggle

Top right "Light"/"Dark" button for switching interface theme; preference saved in browser local storage.

### Responsive Design

Interface layout adjusts automatically based on screen size.

## Usage Instructions

### First Use

1. After starting service, visit `http://127.0.0.1:2048/` in browser

2. **API Key Config Check**:
   - Visit "Settings" tab to check API key status
   - If "No API Key Required" shows, use directly
   - If "API Key Required" shows, verification is needed

3. **API Key Verification Process** (If needed):
   - Enter valid API key in "API Key Management" area
   - Click "Verify Key" button
   - Upon success, interface refreshes to show:
     - Verified status indicator
     - List of keys configured on server (masked)
     - Complete key management features

4. **How to Get Key**:
   - Admins: View `auth_profiles/key.txt` file directly
   - Users: Contact admin to get valid API key
   - Key Format: String of at least 8 characters

### Daily Use

1. Input message in chat interface to test dialogue (uses verified key automatically)
2. View service status via "Server Info" tab
3. Adjust dialogue parameters in "Model Settings" tab
4. Sidebar displays real-time system logs for debugging and monitoring

## Security Mechanism Explanation

- **Tiered Permissions**: Only shows basic info when unverified, full key management when verified
- **Session Persistence**: Verification state persists during browser session, no re-verification needed
- **Secure Display**: All keys masked to protect sensitive info
- **Reset Function**: Reset verification state anytime to re-verify
- **Auto Auth**: Dialogue requests automatically include auth header ensuring secure API calls

## Uses

This Web UI is mainly used for:

- Simple chat testing
- Development debugging
- Quickly verifying if proxy works
- Monitoring server status
- Securely managing API keys
- Conveniently adjusting and testing model parameters

## Troubleshooting

### Logs or Server Info Not Showing

- Check browser developer tools (F12) console and network tabs for errors
- Confirm WebSocket connection (`/ws/logs`) established successfully
- Confirm `/health` and `/api/info` endpoints accessible and returning data

### API Key Management Issues

- **Cannot Verify Key**: Check input format, confirm valid key exists in server's `auth_profiles/key.txt`
- **Verify Success but No Key List**: Check browser console for JS errors, try refreshing page
- **Verification State Lost**: State only valid in current session, closing browser/tab loses state
- **Key Display Abnormal**: Confirm `/api/keys` endpoint returns correct JSON format data

### Chat Function Issues

- **401 Error after Sending**: API key auth failed, re-verify key in settings page
- **Cannot Send Empty Message**: Normal security mechanism, ensure valid input
- **Request Failed**: Check network connection, confirm server running, check browser console and server logs

## Next Steps

After finishing with Web UI, refer to:

- [API Usage Guide](api-usage.md)
- [Troubleshooting Guide](troubleshooting.md)
