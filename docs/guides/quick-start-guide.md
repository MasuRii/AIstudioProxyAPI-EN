# Quick Start Guide

This guide helps you quickly deploy and run the AI Studio Proxy API, suitable for new users to get started fast.

---

## 🎯 Goals

By completing this guide, you will be able to:

- ✅ Successfully run the AI Studio Proxy API server locally
- ✅ Access Google AI Studio via an OpenAI-compatible API
- ✅ Use the built-in Web UI for testing
- ✅ Understand basic configuration and troubleshooting

**Estimated Time**: 15-30 minutes

---

## 📋 Prerequisites

Before starting, ensure your system meets the following requirements:

- ✅ **Python 3.9+** (Recommended 3.10 or 3.11)
- ✅ **Stable Internet Connection** (To access Google AI Studio)
- ✅ **2GB+ Available RAM**
- ✅ **Google Account** (For accessing AI Studio)

### Check Python Version

```bash
python --version
# Or
python3 --version
```

If the version is lower than 3.9, please upgrade Python first.

---

## 🚀 Method 1: One-Click Installation (Recommended for Beginners)

### macOS / Linux

```bash
# Download and execute the installation script
curl -sSL https://raw.githubusercontent.com/CJackHwang/AIstudioProxyAPI/main/scripts/install.sh | bash

# Enter the project directory
cd AIstudioProxyAPI

# Skip to the "Configure Service" step
```

### Windows (PowerShell)

```powershell
# Download and execute the installation script
iwr -useb https://raw.githubusercontent.com/CJackHwang/AIstudioProxyAPI/main/scripts/install.ps1 | iex

# Enter the project directory
cd AIstudioProxyAPI

# Skip to the "Configure Service" step
```

---

## 📦 Method 2: Manual Installation

### Step 1: Install Poetry

**Poetry** is a modern Python dependency management tool used by this project to manage all dependencies.

#### macOS / Linux

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

#### Windows (PowerShell)

```powershell
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
```

#### Using Package Managers (Optional)

```bash
# macOS (Homebrew)
brew install poetry

# Ubuntu/Debian
apt install python3-poetry

# Fedora
dnf install poetry
```

**Verify Installation**:

```bash
poetry --version
```

### Step 2: Clone the Project

```bash
git clone https://github.com/CJackHwang/AIstudioProxyAPI.git
cd AIstudioProxyAPI
```

### Step 3: Install Dependencies

```bash
# Poetry will automatically create a virtual environment and install all dependencies
poetry install
```

This process may take a few minutes, please wait patiently.

### Step 4: Activate Virtual Environment

There are two ways to activate the virtual environment:

**Method A: Enter Shell (Recommended for daily use)**

```bash
poetry shell
```

After activation, your command prompt will show the virtual environment name.

**Method B: Use `poetry run` (Recommended for automation)**

```bash
# Add the poetry run prefix every time you run a command
poetry run python launch_camoufox.py --headless
```

---

## ⚙️ Configure Service

### Step 1: Create Configuration File

```bash
# Copy the configuration template
cp .env.example .env
```

### Step 2: Edit Configuration (Optional)

```bash
# Use your preferred editor
nano .env
# Or
code .env
# Or
vim .env
```

**Basic Configuration Example**:

```env
# Service Port (Default 2048)
PORT=2048

# Streaming Proxy Port (Default 3120, set to 0 to disable)
STREAM_PORT=3120

# Proxy Configuration (If needed)
UNIFIED_PROXY_CONFIG=http://127.0.0.1:7890

# Log Level (DEBUG, INFO, WARNING, ERROR)
SERVER_LOG_LEVEL=INFO
```

**💡 Tip**: You can use the default configuration for the first run and adjust it later as needed.

---

## 🔐 Initial Authentication

Authentication with a Google account is required for the first run to obtain the Cookies needed to access AI Studio.

### Configure Auth Saving

Ensure automatic auth saving is set in the `.env` file:

```env
# [IMPORTANT] Must be set to true to save auth profiles!
AUTO_SAVE_AUTH=true
```

### Use Debug Mode for Authentication

```bash
# Start debug mode (will open a browser window)
poetry run python launch_camoufox.py --debug
```

### Authentication Steps

1. **Browser Window Opens** - Camoufox browser will open automatically.
2. **Login to Google Account** - Log in to your Google account in the browser.
3. **Access AI Studio** - The browser will automatically navigate to the AI Studio page.
4. **Wait for Save** - Authentication information will be automatically saved to the `auth_profiles/saved/` directory.
5. **Check Logs** - The terminal will display a message indicating the auth file was saved successfully.

**Success Indicator**:

```
✅ Auth file saved to: auth_profiles/saved/XXXXXXXX.json
```

### Activate Auth File

Move the saved auth file to the `active` directory:

```bash
# Move auth file from saved to active
mv auth_profiles/saved/*.json auth_profiles/active/
```

### Close Debug Mode

After authentication is complete, press `Ctrl+C` to stop the debug mode server.

---

## 🎮 Daily Operation

After authentication is complete, you have multiple ways to start the service:

### Method 1: Command Line Start (Recommended)

**Headless Mode** (Recommended, runs browser in background):

```bash
poetry run python launch_camoufox.py --headless
```

**Normal Mode** (Shows browser window):

```bash
poetry run python launch_camoufox.py
```

**Virtual Display Mode** (For Linux headless environments):

```bash
poetry run python launch_camoufox.py --virtual-display
```

### Method 2: Direct FastAPI Start (Development/Debug)

```bash
# Start only the API server (does not start browser)
poetry run python -m uvicorn server:app --host 0.0.0.0 --port 2048
```

**Note**: This method requires manually configuring the `CAMOUFOX_WS_ENDPOINT` environment variable.

---

## 🧪 Test Service

### 1. Health Check

Open a browser or use `curl`:

```bash
# Check service status
curl http://127.0.0.1:2048/health

# Expected Output (Success)
{
  "status": "OK",
  "message": "Service running; Queue length: 0.",
  "details": {
    "isPlaywrightReady": true,
    "isBrowserConnected": true,
    "isPageReady": true,
    "workerRunning": true,
    "queueLength": 0
  }
}
```

### 2. View Model List

```bash
curl http://127.0.0.1:2048/v1/models

# Expected Output
{
  "object": "list",
  "data": [
    {
      "id": "gemini-1.5-pro",
      "object": "model",
      "created": 1699999999,
      "owned_by": "google"
    },
    ...
  ]
}
```

### 3. Test Chat Interface

**Non-Streaming Request**:

```bash
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-1.5-pro",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ],
    "stream": false
  }'
```

**Streaming Request**:

```bash
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-1.5-pro",
    "messages": [
      {"role": "user", "content": "Tell me a short story"}
    ],
    "stream": true
  }' --no-buffer
```

### 4. Use Built-in Web UI

Open a browser and visit:

```
http://127.0.0.1:2048
```

**Web UI Features**:

- 💬 Real-time chat testing
- 📊 Service status monitoring
- 🔑 API key management
- 📝 Real-time log viewing

---

## 🔧 Common Issues

### Issue 1: Port Occupied

**Error Message**:

```
Error: Address already in use
```

**Solution**:

```bash
# Find the process occupying the port
# Windows
netstat -ano | findstr 2048

# macOS/Linux
lsof -i :2048

# Modify .env file to use another port
PORT=3048
```

### Issue 2: Auth File Expired

**Symptom**: Unable to access AI Studio after service start, logs show authentication error.

**Solution**:

```bash
# 1. Delete old auth files
rm -rf auth_profiles/active/*.json

# 2. Re-run debug mode authentication
poetry run python launch_camoufox.py --debug

# 3. Re-login to Google Account
```

### Issue 3: Unable to Install Camoufox

**Error Message**:

```
Error downloading Camoufox binary
```

**Solution**:

```bash
# Option A: Use the provided download script
poetry run python fetch_camoufox_data.py

# Option B: Manual download (Requires proxy)
export HTTPS_PROXY=http://127.0.0.1:7890
poetry run camoufox fetch

# Option C: Use version without geoip
pip install camoufox --no-deps
```

### Issue 4: Playwright Dependencies Missing (Linux)

**Error Message**:

```
Error: libgbm-dev not found
```

**Solution**:

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y libgbm-dev libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2

# Or use Playwright auto-install
playwright install-deps
```

### Issue 5: Model List Empty

**Symptom**: `/v1/models` returns an empty list or only default models.

**Solution**:

```bash
# 1. Check service status
curl http://127.0.0.1:2048/health

# 2. View logs
tail -f logs/app.log

# 3. Check auth files
ls -la auth_profiles/active/

# 4. Wait for service to fully start (may take 30-60 seconds)
```

---

## 📚 Next Steps

Congratulations! You have successfully run the AI Studio Proxy API.

### Recommended Reading

1. **[Environment Configuration Guide](environment-configuration.md)** - Understand all configuration options
2. **[API Usage Guide](api-usage.md)** - Learn how to use the API
3. **[OpenAI Compatibility Note](openai-compatibility.md)** - Understand differences from OpenAI API
4. **[Web UI Guide](webui-guide.md)** - Explore Web UI features

### Advanced Topics

- **[Docker Deployment](../docker/README-Docker.md)** - Deploy using Docker containers
- **[Streaming Modes Explained](streaming-modes.md)** - Understand the three-layer response mechanism
- **[Advanced Configuration](advanced-configuration.md)** - Performance optimization and advanced features
- **[Troubleshooting Guide](troubleshooting.md)** - More solutions to problems

---

## 🆘 Get Help

If you encounter problems, you can:

1. **Check Documentation** - This project contains detailed documentation
2. **Check Logs** - `logs/app.log` contains detailed runtime logs
3. **Check Snapshots** - `errors_py/` directory contains page snapshots on error
4. **Submit Issue** - [GitHub Issues](https://github.com/CJackHwang/AIstudioProxyAPI/issues)
5. **Community Discussion** - [Linux.do Community](https://linux.do/)

---

## 🎉 Success Checklist

- [ ] Service started successfully, no error logs
- [ ] `/health` endpoint returns `"status": "OK"`
- [ ] `/v1/models` returns model list
- [ ] Successfully completed one chat request (non-streaming)
- [ ] Successfully completed one chat request (streaming)
- [ ] Web UI is accessible
- [ ] Real-time logs are visible

All checked? 🎊 Congratulations, you have mastered the basic usage!

---

Enjoy using it! Feedback is welcome if you have any questions.
