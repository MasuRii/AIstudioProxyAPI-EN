# Installation Guide

This document provides detailed installation steps and environment configuration instructions based on Poetry.

## 🔧 System Requirements

### Basic Requirements

- **Python**: 3.9+ (Recommended 3.10+ or 3.11+)
  - **Recommended Version**: Python 3.11+ for best performance and compatibility
  - **Minimum Requirement**: Python 3.9
  - **Fully Supported**: Python 3.9, 3.10, 3.11, 3.12, 3.13
- **Poetry**: 1.4+ (Modern Python dependency management tool)
- **Git**: For cloning the repository (Recommended)
- **Google AI Studio Account**: Must be able to access and use normally
- **Node.js**: 18+ (Optional, for frontend development. If not needed, use `--skip-frontend-build` to skip build)

### System Dependencies

- **Linux**: `xvfb` (Virtual display, optional)
  - Debian/Ubuntu: `sudo apt-get update && sudo apt-get install -y xvfb`
  - Fedora: `sudo dnf install -y xorg-x11-server-Xvfb`
- **macOS**: Usually no extra dependencies required
- **Windows**: Usually no extra dependencies required

## 🚀 Quick Installation (Recommended)

### One-Click Installation Script

```bash
# macOS/Linux Users
curl -sSL https://raw.githubusercontent.com/CJackHwang/AIstudioProxyAPI/main/scripts/install.sh | bash

# Windows Users (PowerShell)
iwr -useb https://raw.githubusercontent.com/CJackHwang/AIstudioProxyAPI/main/scripts/install.ps1 | iex
```

## 📋 Manual Installation Steps

### 1. Install Poetry

If you haven't installed Poetry yet, please install it first:

```bash
# macOS/Linux
curl -sSL https://install.python-poetry.org | python3 -

# Windows (PowerShell)
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -

# Or using package managers
# macOS: brew install poetry
# Ubuntu/Debian: apt install python3-poetry
# Windows: winget install Python.Poetry
```

### 2. Clone Repository

```bash
git clone https://github.com/CJackHwang/AIstudioProxyAPI.git
cd AIstudioProxyAPI
```

### 3. Install Dependencies

Poetry will automatically create a virtual environment and install all dependencies:

```bash
# Install production dependencies
poetry install

# Install including development dependencies (Recommended for developers)
poetry install --with dev
```

**Poetry Advantages**:

- ✅ Automatically creates and manages virtual environments
- ✅ Dependency resolution and version locking (`poetry.lock`)
- ✅ Distinguishes between production and development dependencies
- ✅ Semantic versioning

### 4. Activate Virtual Environment

```bash
# Activate the virtual environment created by Poetry
poetry env activate

# Or prefix every command with poetry run
poetry run python --version
```

### 5. Download Camoufox Browser

```bash
# Download Camoufox browser in Poetry environment
poetry run camoufox fetch

# Or in the activated environment
camoufox fetch
```

**Key Dependencies** (Managed automatically by Poetry versions):

- **FastAPI**: High-performance Web framework, providing API services
- **Pydantic**: Modern data validation library
- **Uvicorn**: High-performance ASGI server
- **Playwright**: Browser automation, page interaction, and network interception
- **Camoufox**: Anti-fingerprinting browser, includes geoip data and enhanced stealth
- **WebSockets**: For real-time log transmission, status monitoring, and Web UI communication
- **aiohttp**: Asynchronous HTTP client
- **python-dotenv**: Environment variable management

### 6. Install Playwright Dependencies & Browser (Optional)

Although Camoufox uses its own Firefox, on some Linux distributions you might need to install system dependencies, or developers might need standard Playwright browsers for debugging:

```bash
# 1. Install system dependencies (Recommended for Linux users)
poetry run playwright install-deps firefox

# 2. Install standard Playwright browser (For debugging or development only)
poetry run playwright install
```

If `camoufox fetch` fails due to network issues, try running the project's [`fetch_camoufox_data.py`](../fetch_camoufox_data.py) script (see [Troubleshooting Guide](troubleshooting.md)).

## 🔍 Verify Installation

### Check Poetry Environment

```bash
# View Poetry environment info
poetry env info

# View installed dependencies
poetry show

# Check Python version
poetry run python --version
```

### Check Key Components

```bash
# Check Camoufox
poetry run camoufox --version

# Check FastAPI
poetry run python -c "import fastapi; print(f'FastAPI: {fastapi.__version__}')"

# Check Playwright
poetry run python -c "import playwright; print('Playwright: OK')"
```

## 🚀 How to Start the Service

After completing installation and environment configuration, it is highly recommended to copy `.env.example` to `.env` and modify it according to your needs. This will greatly simplify subsequent startup commands.

```bash
# Copy configuration template
cp .env.example .env

# Edit configuration file
nano .env  # Or use another editor
```

After configuration, you can choose one of the following ways to start the service:

### 1. Command Line Start (Recommended)

For users familiar with the command line, use the `launch_camoufox.py` script to start the service directly.

```bash
# Start in headless mode, this is the common way for server deployment
poetry run python launch_camoufox.py --headless

# Start in debug mode, shows browser interface
poetry run python launch_camoufox.py --debug
```

You can control startup behavior by adding different parameters, e.g.:

- `--headless`: Run browser in background, no interface shown.
- `--debug`: Show browser interface at startup for easy debugging.
- For more parameters, see [Advanced Configuration Guide](advanced-configuration.md).

### 2. Docker Start

If you are familiar with Docker, you can also deploy the service using containers. This method provides better environment isolation.

For detailed Docker startup instructions, please see:

- **[Docker Deployment Guide](../docker/README-Docker.md)**

## Multi-Platform Guide

### macOS / Linux

- Installation is usually smooth. Ensure Python and pip are correctly installed and configured in system PATH.
- Use `source venv/bin/activate` to activate the virtual environment (if not using Poetry shell).
- `playwright install-deps firefox` might require system package managers (like `apt`, `dnf`, `brew`) to install some dependency libraries. If the command fails, install missing system packages according to the error prompt.
- Firewalls usually don't block local access, but if accessing from another machine, ensure the port (default 2048) is open.
- For Linux users, consider starting with the `--virtual-display` flag (requires pre-installed `xvfb`), which uses Xvfb to create a virtual display environment to run the browser, potentially helping to further reduce detection risks.

### Windows

#### Native Windows

- Ensure "Add Python to PATH" is checked when installing Python.
- Windows Firewall might block Uvicorn/FastAPI listening ports. If connection issues occur, check firewall settings.
- `playwright install-deps` has limited effect on native Windows, but running `camoufox fetch` ensures the correct browser is downloaded.
- **Recommended to start with `python launch_camoufox.py --headless`**.

#### WSL (Windows Subsystem for Linux)

- **Recommended**: For users used to Linux environments, WSL (especially WSL2) offers a better experience.
- Inside the WSL environment, follow the **macOS / Linux** steps for installation.
- Network access notes:
  - Accessing WSL service from Windows: Usually via `localhost`.
  - Accessing from LAN: May require configuring Windows Firewall and WSL network settings.
- All commands should be executed within the WSL terminal.
- Running `--debug` mode in WSL: If WSLg or X Server is configured, you can see the browser interface. Otherwise, headless mode is recommended.

## Configure Environment Variables (Recommended)

After installation, it is strongly recommended to configure the `.env` file to simplify future use:

### Create Configuration File

```bash
# Copy configuration template
cp .env.example .env

# Edit configuration file
nano .env  # Or use another editor
```

### Basic Configuration Example

```env
# Service Port Configuration
DEFAULT_FASTAPI_PORT=2048
STREAM_PORT=3120

# Proxy Configuration (If needed)
# UNIFIED_PROXY_CONFIG=http://127.0.0.1:7890

# Log Configuration
SERVER_LOG_LEVEL=INFO
DEBUG_LOGS_ENABLED=false
```

After configuration, the startup command becomes very simple:

```bash
# Simple start, no complex parameters needed
python launch_camoufox.py --headless
```

For detailed configuration instructions, see [Environment Configuration Guide](environment-configuration.md).

## Optional: Configure API Keys

You can also choose to configure API keys to protect your service:

### Create Key File

Create a `key.txt` file in the `auth_profiles` directory (if it doesn't exist):

```bash
# Create directory and key file
mkdir -p auth_profiles && touch auth_profiles/key.txt

# Add key (one per line)
echo "your-first-api-key" >> auth_profiles/key.txt
```

### Key Format Requirements

- One key per line
- At least 8 characters
- Supports empty lines and comment lines (starting with `#`)
- Use UTF-8 encoding

### Security Notes

- **No Key File**: Service requires no authentication, anyone can access the API
- **Key File Exists**: All API requests require a valid key
- **Key Protection**: Keep the key file safe, do not commit it to version control systems

## Next Steps

After installation is complete, please refer to:

- **[Environment Configuration Guide](environment-configuration.md)** - ⭐ Recommended to configure first
- [First Run & Authentication Setup](authentication-setup.md)
- [Daily Usage Guide](daily-usage.md)
- [API Usage Guide](api-usage.md)
- [Troubleshooting Guide](troubleshooting.md)
