# Troubleshooting Guide

This document provides solutions and debugging methods for common problems with the AI Studio Proxy API project, covering installation, configuration, operation, API usage, and more.

## Quick Diagnosis

Before diving into specific issues, perform a quick diagnosis:

### 1. Check Service Status

```bash
# Check if service is running normally
curl http://127.0.0.1:2048/health

# Check API info
curl http://127.0.0.1:2048/api/info
```

### 2. Check Configuration File

```bash
# Check if .env file exists
ls -la .env

# Check key configuration items
grep -E "(PORT|SCRIPT_INJECTION|LOG_LEVEL)" .env
```

### 3. Check Logs

```bash
# View latest logs
tail -f logs/app.log

# View error logs
grep -i error logs/app.log
```

## Installation Issues

### Python Version Compatibility

**Python Version Too Low**:

- **Minimum Requirement**: Python 3.9+
- **Recommended Version**: Python 3.10+ or 3.11+
- **Check Version**: `python --version`

**Common Version Errors**:

```bash
# Errors that might appear in Python 3.8 or lower
TypeError: 'type' object is not subscriptable
SyntaxError: invalid syntax (Type hint related)

# Solution: Upgrade Python Version
# macOS (Using Homebrew)
brew install python@3.11

# Ubuntu/Debian
sudo apt update && sudo apt install python3.11

# Windows: Download and install from python.org
```

**Poetry Environment Python Version**:

```bash
# Check Python version in Poetry environment
poetry run python --version

# If incorrect, specify Python version to reinstall environment
poetry env use python3.11
poetry install
```

### `poetry install` Failed (Camoufox Related)

- **Issue**: Error during dependency installation, indicating `camoufox` or `geoip` related errors.
- **Cause**: Likely network issues or missing compilation environment.
- **Solution**: Try modifying `pyproject.toml`, temporarily remove `extras = ["geoip"]`, then run `poetry lock && poetry install`.

### `camoufox fetch` Failed

- Common causes are network issues or SSL certificate verification failure.
- Try running the project's [`poetry run python fetch_camoufox_data.py`](../fetch_camoufox_data.py) script, which attempts to download with SSL verification disabled (security risk, use only in trusted network environments).

### `playwright install-deps` Failed

- Usually Linux system missing necessary libraries. Read error message carefully, install missing system packages as prompted (e.g., `libgbm-dev`, `libnss3`, etc.).
- Ensure running with `poetry run playwright install-deps` to install in the correct environment.

## Startup Issues

### `launch_camoufox.py` Startup Error

- **Browser Not Found**: Check if Camoufox is correctly downloaded via `poetry run camoufox fetch`.
- **Dependency Missing**: Linux systems might need `poetry run playwright install-deps`.
- **View Error**: Check terminal output for specific error messages from Camoufox library.
- **Process Conflict**: Ensure no other Camoufox or Playwright process conflicts.

### Port Occupied

If [`server.py`](../server.py) startup prompts port (`2048`) occupied:

- When starting with `python launch_camoufox.py --headless`, you can check port occupancy info directly in terminal.
- Manually find and kill occupying process:

  ```bash
  # Windows
  netstat -ano | findstr 2048

  # Linux/macOS
  lsof -i :2048
  ```

- Or modify `--server-port` parameter in [`launch_camoufox.py`](../launch_camoufox.py).

### Docker Auth Issue (Headless)

**Issue**: Docker container fails auth after startup, or stuck at login page.

**Cause**: Docker containers typically run in Headless mode, unable to perform interactive Google login.

**Solution**:

1. **Generate Auth on Host**: On the host running Docker (or any machine that can run a browser), run the program in debug mode:
   ```bash
   poetry run python launch_camoufox.py --debug
   ```
2. **Complete Login**: Complete Google login in the popped-up browser.
3. **Mount File**: Mount the generated `auth_profiles/active/` directory into the Docker container.

### Camoufox Startup Proxy Error

**Symptom**: Without proxy env var configured, Camoufox startup fails:

```
Error: proxy: expected object, got null
```

**Cause**: Camoufox 0.4.11's utils.py unconditionally passes proxy parameter to Playwright, even if value is None.

**Fix**: Modify Camoufox source file (located in Poetry virtual environment):

```bash
# Find file location
find $(poetry env info --path) -name "utils.py" | grep camoufox
# Usually at: .venv/lib/python3.x/site-packages/camoufox/utils.py
```

In `launch_options` function, change:

```python
return {
    ...
    "proxy": proxy,
    ...
}
```

To:

```python
result = {
    ...  # Delete "proxy": proxy, other configs remain unchanged
}
if proxy is not None:
    result["proxy"] = proxy
return result
```

## Authentication Issues

### Auth Failure (Especially Headless Mode)

**Most Common**: `.json` file in `auth_profiles/active/` is expired or invalid.

**Solution**:

1. Delete files under `active`.
2. Re-run [`poetry run python launch_camoufox.py --debug`](../launch_camoufox.py) to generate new auth file.
3. Move new file to `active` directory.
4. Confirm only one `.json` file in `active` directory.

### Check Auth Status

- Check [`server.py`](../server.py) logs (via Web UI log sidebar or `logs/app.log`).
- Look for explicit mention of login redirection.

## Streaming Proxy Service Issues

### Port Conflict

Ensure streaming proxy service port (`3120` or custom `--stream-port`) is not occupied by other applications.

### Proxy Configuration Issues

**Recommended using .env configuration**:

```env
# Unified proxy configuration
UNIFIED_PROXY_CONFIG=http://127.0.0.1:7890
# Or disable proxy
UNIFIED_PROXY_CONFIG=
```

**Common Issues**:

- **Proxy Not Working**: Ensure `UNIFIED_PROXY_CONFIG` is set in `.env` or use `--internal-camoufox-proxy` parameter.
- **Proxy Conflict**: Use `UNIFIED_PROXY_CONFIG=` or `--internal-camoufox-proxy ''` to explicitly disable proxy.
- **Proxy Connection Failed**: Check if proxy server is available, verify proxy address format.

### Three-Layer Response Mechanism Issues

**Streaming Response Interrupted**:

- Check integrated streaming proxy status (port 3120).
- Try disabling streaming proxy for testing: Set `STREAM_PORT=0` in `.env`.
- Check `/health` endpoint for status of each layer.

**Response Acquisition Failed**:

1. **Layer 1 Failure**: Check if streaming proxy service is running normally.
2. **Layer 2 Failure**: Verify Helper service configuration and auth file.
3. **Layer 3 Failure**: Check Playwright browser connection status.

For details, see [Streaming Modes Explained](streaming-modes.md).

### Self-Signed Certificate Management

Integrated streaming proxy service generates self-signed root certificates in `certs` folder.

**Certificate Deletion and Regeneration**:

- Can delete root certificates (`ca.crt`, `ca.key`) in `certs` directory, code will regenerate at next startup.
- **Important**: When deleting root certificates, **strongly recommended to delete all other files in `certs` directory** to avoid trust chain errors.

## API Request Issues

### 5xx / 499 Errors

- **503 Service Unavailable**: [`server.py`](../server.py) not fully ready.
- **504 Gateway Timeout**: AI Studio response slow or processing timeout.
- **502 Bad Gateway**: AI Studio page returns error. Check `errors_py/` snapshots.
- **500 Internal Server Error**: [`server.py`](../server.py) internal error. Check logs and `errors_py/` snapshots.
- **499 Client Closed Request**: Client disconnected prematurely.

### Client Unable to Connect

- Confirm API base URL is correct (`http://<ServerIPorLocalhost>:Port/v1`, default port 2048).
- Check [`server.py`](../server.py) logs for errors.

### AI Reply Incomplete/Malformed

- AI Studio Web UI output unstable. Check `errors_py/` snapshots.

## Page Interaction Issues

### Auto Clear Context Failed

- Check warnings in main server logs.
- Likely AI Studio page update caused CSS selectors in [`config/selectors.py`](../config/selectors.py) to fail.
- Check `errors_py/` snapshots, compare actual page elements to update selector constants.

### AI Studio Page Update Breaking Features

If AI Studio updated page structure or CSS class names:

1. Check main server logs for warnings or errors.
2. Check error snapshots in `errors_py/` directory.
3. Compare actual page elements, update corresponding CSS selector constants in [`config/selectors.py`](../config/selectors.py).

### Model Parameters Not Taking Effect

This might be because `isAdvancedOpen` in AI Studio page's `localStorage` is not correctly set to `true`:

- Proxy service attempts to auto-correct these settings and reload page on startup.
- If issue persists, try clearing browser cache and `localStorage` then restart proxy service.

## Web UI Issues

### Logs or Server Info Not Showing

- Check browser developer tools (F12) console and network tabs for errors.
- Confirm WebSocket connection (`/ws/logs`) established successfully.
- Confirm `/health` and `/api/info` endpoints accessible.

## API Key Issues

### key.txt File Issues

**File Not Exists or Empty**:

- System automatically creates empty `auth_profiles/key.txt` file.
- Empty file means no API key verification required.
- To enable verification, manually add keys to file.

**File Permission Issues**:

```bash
# Check file permissions
ls -la key.txt

# Fix permissions
chmod 644 key.txt
```

**File Format Issues**:

- Ensure one key per line, no extra spaces.
- Support empty lines and comment lines starting with `#`.
- Use UTF-8 encoding.

### API Auth Failure

**401 Unauthorized Error**:

- Check if request header contains correct auth info.
- Verify if key exists in `key.txt` file.
- Confirm using correct auth header format:
  ```bash
  Authorization: Bearer your-api-key
  # Or
  X-API-Key: your-api-key
  ```

**Key Verification Logic**:

- If `key.txt` empty, no requests require auth.
- If `key.txt` has content, all `/v1/*` requests require auth.
- Excluded paths: `/v1/models`, `/health`, `/docs` etc.

### Web UI Key Management Issues

**Cannot Verify Key**:

- Check input key format, ensure at least 8 characters.
- Confirm server `key.txt` contains the key.
- Check network connection, confirm `/api/keys/test` endpoint accessible.

**Verify Success but No Key List**:

- Check browser console for JS errors.
- Confirm `/api/keys` endpoint returns correct JSON format data.
- Try refreshing page to re-verify.

**Verification State Lost**:

- Verification state only valid in current browser session.
- Closing browser or tab loses verification state.
- Need to re-verify to view key list.

**Key Display Abnormal**:

- Confirm server returns correct key data format.
- Check if key masking function works normally.
- Verify `maskApiKey` function execution.

### Client Configuration Issues

**Open WebUI Config**:

- API Base URL: `http://127.0.0.1:2048/v1`
- API Key: Enter valid key or leave blank (if server doesn't require auth).
- Confirm port matches server listening port.

**Other Client Config**:

- Check if client supports `Authorization: Bearer` auth header.
- Confirm client handles 401 auth error correctly.
- Verify client timeout settings are reasonable.

### Key Management Best Practices

**Security Recommendations**:

- Rotate API keys regularly.
- Do not expose full keys in logs or public places.
- Use sufficiently complex keys (Recommended 16+ characters).
- Limit key usage scope and permissions.

**Backup Recommendations**:

- Regularly backup `key.txt` file.
- Record key creation time and usage.
- Establish key rotation mechanism.

### Chat Function Issues

- **401 Error after Sending**: API key auth failed, re-verify key.
- **Cannot Send Empty Message**: Normal security mechanism.
- **Request Failed**: Check network, confirm server running.

## Script Injection Issues

### Script Injection Not Enabled

**Check Configuration**:

```bash
# Check config in .env file
grep SCRIPT_INJECTION .env
grep USERSCRIPT_PATH .env
```

**Common Issues**:

- `ENABLE_SCRIPT_INJECTION=false` - Feature disabled.
- Script file path incorrect.
- Script file does not exist or unreadable.

**Solution**:

```bash
# Enable script injection
echo "ENABLE_SCRIPT_INJECTION=true" >> .env

# Check script file existence
ls -la browser_utils/more_models.js

# Check file permissions
chmod 644 browser_utils/more_models.js
```

### Model Not Showing in List

**Frontend Check**:

1. Open browser developer tools (F12).
2. Check console for JS errors.
3. Check network tab for model list requests.

**Backend Check**:

```bash
# View script injection related logs
poetry run python launch_camoufox.py --debug | grep -i "script\|inject\|model"

# Check API response
curl http://localhost:2048/v1/models | jq '.data[] | select(.injected == true)'
```

**Common Causes**:

- Script format error, unable to parse `MODELS_TO_INJECT` array.
- Network interception failed, script injection not effective.
- Model name format incorrect.

### Script Parsing Failed

**Check Script Format**:

```javascript
// Ensure script contains correct model array format
const MODELS_TO_INJECT = [
  {
    name: "models/your-model-name",
    displayName: "Your Model Display Name",
    description: "Model description",
  },
];
```

**Debugging Steps**:

1. Verify script file JavaScript syntax.
2. Check model array format correctness.
3. Confirm model name starts with `models/`.

### Network Interception Failed

**Check Playwright Status**:

- Confirm browser context created normally.
- Check network routing set correctly.
- Verify request URL matching rules.

**Debugging Method**:

```bash
# Enable verbose logs to view network interception status
export DEBUG_LOGS_ENABLED=true
poetry run python launch_camoufox.py --debug
```

**Common Errors**:

- Browser context creation failed.
- Network routing setup exception.
- Request URL does not match interception rules.

### Model Parsing Issues

**Script Format Error**:

```bash
# Check script file syntax
node -c browser_utils/more_models.js
```

**File Permission Issue**:

```bash
# Check file permissions
ls -la browser_utils/more_models.js

# Fix permissions
chmod 644 browser_utils/more_models.js
```

**Script File Not Found**:

- System silently skips non-existent script file.
- Check `USERSCRIPT_PATH` environment variable.
- Ensure script file contains valid `MODELS_TO_INJECT` array.

### Performance Issues

**Script Injection Latency**:

- Network interception might add slight latency.
- Large number of injected models might affect page loading.
- Recommended to limit injected models (< 20).

**Memory Usage**:

- Script content is cached in memory.
- Large script files might increase memory usage.
- Regularly restart service to release memory.

### Debugging Tips

**Enable Detailed Logs**:

```bash
# Add to .env file
DEBUG_LOGS_ENABLED=true
TRACE_LOGS_ENABLED=true
SERVER_LOG_LEVEL=DEBUG
```

**Check Injection Status**:

```bash
# View logs related to script injection
tail -f logs/app.log | grep -i "script\|inject"
```

**Verify Model Injection**:

```bash
# Check API returned model list
curl -s http://localhost:2048/v1/models | jq '.data[] | select(.injected == true) | {id, display_name}'
```

### Disable Script Injection

If severe issues occur, temporarily disable script injection:

```bash
# Method 1: Modify .env file
echo "ENABLE_SCRIPT_INJECTION=false" >> .env

# Method 2: Use environment variable
export ENABLE_SCRIPT_INJECTION=false
poetry run python launch_camoufox.py --headless

# Method 3: Delete script file (Temporary)
mv browser_utils/more_models.js browser_utils/more_models.js.bak
```

## Logging and Debugging

### View Detailed Logs

- `logs/app.log`: FastAPI server detailed logs.
- `logs/launch_app.log`: Launcher logs.
- Web UI Right Sidebar: Real-time display of `INFO` and above logs.

### Environment Variable Control

Control log verbosity via environment variables:

```bash
# Set log level
export SERVER_LOG_LEVEL=DEBUG

# Enable detailed debug logs
export DEBUG_LOGS_ENABLED=true

# Enable trace logs (Usually not needed)
export TRACE_LOGS_ENABLED=true
```

### Comprehensive Snapshots

System automatically creates directory containing detailed debug info in `errors_py/YYYY-MM-DD/` on error. These snapshots are crucial for diagnosing complex issues (like interaction failure in headless mode).

**Snapshot Contents**:

1.  **screenshot.png**: Page screenshot at error time.
2.  **dom_dump.html**: Complete page HTML source.
3.  **dom_structure.txt**: Human-readable DOM tree structure for analyzing element hierarchy.
4.  **console_logs.txt**: Browser console logs (including errors and warnings).
5.  **network_requests.json**: Recent network request and response records.
6.  **playwright_state.json**: Playwright internal state (URL, viewport, key element states).
7.  **metadata.json**: Error metadata (timestamp, error type, environment configuration).

## Performance Issues

### Asyncio Related Errors

You might see `asyncio` related errors in logs, especially when network connection is unstable. If core proxy function is still available, these errors might not directly affect main features.

### First Access Performance to New Host

When accessing a new HTTPS host via streaming proxy for the first time, service needs to dynamically generate certificate, which might be time-consuming. Once generated and cached, subsequent access will be significantly faster.

## Get Help

If issue persists:

1. Check project [GitHub Issues](https://github.com/CJackHwang/AIstudioProxyAPI/issues).
2. Submit new Issue including:
   - Detailed error description
   - Relevant log file content
   - System environment info
   - Reproduction steps

## Next Steps

After troubleshooting, please refer to:

- [Script Injection Guide](script_injection_guide.md) - Detailed script injection guide
- [Log Control Guide](logging-control.md)
- [Advanced Configuration Guide](advanced-configuration.md)

---

## Authentication Rotation Failures

### Error: "Rotation Failed: No available auth profiles found"

**Symptom:**
The server log shows a critical error `Rotation Failed: No available auth profiles found`, and the system may enter "Emergency Operation Mode." This typically happens after a series of token limit, quota, or rate limit errors.

**Cause:**
This error is not a bug in the rotation logic. It means the system has run out of healthy, usable authentication profiles. The "smart rotation" mechanism has scanned all profile directories (`auth_profiles/saved`, `auth_profiles/active`, and `auth_profiles/emergency`) and found that every single profile is currently in a "cooldown" state.

A profile is put into cooldown if:
1.  It has just hit a rate limit or quota limit.
2.  It failed a "canary test," meaning it was selected for rotation but was found to be unhealthy or expired.

**Strategic Solution: Managing Profile Pools**

You are correct that simply copying the same profile into all three directories (`saved`, `active`, `emergency`) will **not** solve the problem. The cooldown is tied to the profile's file path and, more importantly, to the underlying account that is rate-limited.

The directories are meant to hold **different, unique** profiles to create layers of resilience:

1.  **`auth_profiles/saved` (Primary Pool):** This should be your main collection of healthy, unique profiles. The system will primarily use these.
2.  **`auth_profiles/emergency` (Backup Pool):** This should contain a separate, smaller set of unique profiles that are *only* used when the primary pool is completely exhausted. Do not duplicate profiles from the `saved` directory here.
3.  **`auth_profiles/active`:** This directory is for internal state management of the currently active profile. You should not place files here manually.

**How to Fix and Prevent This Error:**

1.  **Immediate Action: Wait.** The system will automatically recover once the cooldown timers on the profiles expire. You can see the cooldown duration in the logs when a profile is placed on cooldown.
2.  **Long-Term Solution: Increase Profile Diversity.** The most effective way to prevent this is to increase the total number of **unique** authentication profiles in your `auth_profiles/saved` and `auth_profiles/emergency` directories. A larger and more diverse pool of profiles makes it statistically much less likely that all of them will be on cooldown at the same time.
3.  **Review Cooldown Timers:** If this happens frequently, you can review the `RATE_LIMIT_COOLDOWN_SECONDS` and `QUOTA_EXCEEDED_COOLDOWN_SECONDS` settings in the `config/timeouts.py` file, but the primary solution should be to add more profiles.
