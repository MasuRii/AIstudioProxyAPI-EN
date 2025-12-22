# Platform Differences Guide

This document details the differences and considerations for AI Studio Proxy API on different operating systems (Windows, macOS, Linux).

---

## 📋 Table of Contents

- [General Requirements](#general-requirements)
- [Windows](#windows)
- [macOS](#macos)
- [Linux](#linux)
- [Docker Environment](#docker-environment)
- [Performance Comparison](#performance-comparison)

---

## General Requirements

All platforms need to meet the following basic requirements:

- **Python**: >=3.9, <4.0 (Recommended 3.10 or 3.11)
- **Memory**: Recommended 2GB+ available RAM
- **Disk**: At least 1GB available space
- **Network**: Stable internet connection

---

## Windows

### System Requirements

- **OS**: Windows 10 or later
- **Architecture**: x86_64
- **PowerShell**: 5.1 or later (Built-in with Windows 10)

### Install Python

**Method 1: Official Installer** (Recommended)

1. Visit [python.org](https://www.python.org/downloads/)
2. Download Python 3.10+ installer for Windows
3. Run installer, **Check "Add Python to PATH"**
4. Verify installation:
   ```powershell
   python --version
   ```

**Method 2: Windows Store**

```powershell
# Install Python 3.11 from Microsoft Store
# Search "Python 3.11" and install
```

**Method 3: Chocolatey**

```powershell
choco install python311
```

### Install Poetry

**PowerShell**:

```powershell
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
```

**Add Poetry to PATH**:

```powershell
$env:Path += ";$env:APPDATA\Python\Scripts"
```

### Platform Specific Notes

#### 1. Virtual Environment Activation

**PowerShell**:

```powershell
# Poetry Shell
poetry shell

# Or use poetry run
poetry run python launch_camoufox.py --headless
```

**CMD**:

```cmd
poetry shell
```

#### 2. Path Separator

Windows uses backslash `\`, but Python code uses `/` or `os.path.join()` handles it automatically.

**Config File Path**:

```env
# Use forward slash or double backslash in .env file
USERSCRIPT_PATH=browser_utils/more_models.js
# Or
USERSCRIPT_PATH=browser_utils\\more_models.js
```

#### 3. uvloop Unavailable

uvloop supports only Linux and macOS, but the project handles it automatically:

```python
# Configured in pyproject.toml
uvloop = {version = "*", markers = "sys_platform != 'win32'"}
```

Windows will automatically use standard asyncio event loop, functionality is fully normal.

#### 4. Port Occupancy Check

```powershell
# Check port occupancy
netstat -ano | findstr 2048

# End process
taskkill /PID <ProcessID> /F
```

#### 5. Firewall Configuration

First run might require allowing Python through firewall:

1. Windows Firewall prompt will pop up
2. Select "Allow access"
3. Or manually add rule:
   - Open "Windows Defender Firewall"
   - Click "Allow an app or feature through Windows Defender Firewall"
   - Add Python and Poetry

#### 6. Long Path Support

If you encounter path length limits:

1. Open Registry Editor (regedit)
2. Navigate to: `HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\FileSystem`
3. Set `LongPathsEnabled` to `1`
4. Restart computer

#### 7. Timezone Support (tzdata)

Windows does not have built-in IANA timezone database like Linux/macOS. This project depends on `tzdata` package to provide timezone support.

- **Auto Install**: Poetry will automatically install `tzdata` based on `pyproject.toml`.
- **Troubleshooting**: If `ZoneInfoNotFoundError` occurs, check if `tzdata` is installed:
  ```powershell
  poetry run pip show tzdata
  ```

### Recommended Terminals

- **Windows Terminal** (Recommended): Modern, supports multiple tabs
- **PowerShell 7+**: Cross-platform, powerful
- **Git Bash**: Unix-like environment

### Common Issues

**Issue**: `poetry` command not found

**Solution**:

```powershell
# Check Poetry install path
$env:APPDATA\Python\Scripts\poetry --version

# Add to PATH
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";$env:APPDATA\Python\Scripts", "User")
```

**Issue**: SSL Certificate Error

**Solution**:

```powershell
# Temporarily disable SSL verification (Not recommended for production)
$env:PYTHONHTTPSVERIFY = "0"

# Or install certificates
pip install --upgrade certifi
```

---

## macOS

### System Requirements

- **OS**: macOS 10.15 (Catalina) or later
- **Architecture**: x86_64 or ARM64 (Apple Silicon)
- **Xcode Command Line Tools**: Auto or manual install

### Install Python

**Method 1: Homebrew** (Recommended)

```bash
# Install Homebrew (If not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.11
brew install python@3.11

# Verify installation
python3 --version
```

**Method 2: pyenv** (Recommended for Developers)

```bash
# Install pyenv
brew install pyenv

# Install Python 3.11
pyenv install 3.11

# Set global version
pyenv global 3.11

# Verify
python --version
```

**Method 3: Official Installer**

1. Visit [python.org](https://www.python.org/downloads/)
2. Download macOS universal installer
3. Run `.pkg` file to install

### Install Poetry

```bash
curl -sSL https://install.python-poetry.org | python3 -

# Or use Homebrew
brew install poetry
```

### Platform Specific Notes

#### 1. Apple Silicon (M1/M2/M3)

Most dependencies support ARM64 architecture, but Rosetta 2 might be needed:

```bash
# Install Rosetta 2 (If needed)
softwareupdate --install-rosetta
```

**Confirm Architecture**:

```bash
# Check Python architecture
python3 -c "import platform; print(platform.machine())"
# arm64 = Apple Silicon native
# x86_64 = Intel or Rosetta 2
```

**Use x86_64 version** (If compatibility issues occur):

```bash
# Run under Rosetta 2
arch -x86_64 python3 script.py
```

#### 2. Permission Issues

macOS needs to grant terminal permissions:

```bash
# If "Operation not permitted" error occurs
# Open "System Preferences" -> "Security & Privacy" -> "Privacy" -> "Full Disk Access"
# Add "Terminal" or "iTerm"
```

#### 3. Certificate Issues

```bash
# Install macOS certificates
/Applications/Python\ 3.11/Install\ Certificates.command

# Or manual install
pip install --upgrade certifi
```

#### 4. Virtual Display (Optional)

macOS has GUI by default, but if virtual display is needed:

```bash
# Install Xvfb (via XQuartz)
brew install --cask xquartz

# Use after restart
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99
```

#### 5. Port Occupancy Check

```bash
# Check port occupancy
lsof -i :2048

# End process
kill -9 <PID>
```

### Recommended Terminals

- **iTerm2** (Recommended): Powerful, customizable
- **Terminal.app**: Built-in, simple enough
- **Warp**: Modern, AI assisted

### Common Issues

**Issue**: `command not found: poetry`

**Solution**:

```bash
# Add Poetry to PATH
export PATH="$HOME/.local/bin:$PATH"

# Add permanently (zsh)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Add permanently (bash)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bash_profile
source ~/.bash_profile
```

**Issue**: SSL Certificate Error

**Solution**:

```bash
# Install certificates
/Applications/Python\ 3.11/Install\ Certificates.command
```

---

## Linux

### System Requirements

- **Distro**: Ubuntu 20.04+, Debian 11+, Fedora 35+, Arch Linux etc.
- **Architecture**: x86_64 or ARM64
- **Dependencies**: Depends on distro

### Install Python

**Ubuntu/Debian**:

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev
```

**Fedora**:

```bash
sudo dnf install python3.11 python3.11-devel
```

**Arch Linux**:

```bash
sudo pacman -S python
```

### Install Poetry

```bash
curl -sSL https://install.python-poetry.org | python3 -

# Or use package manager
# Ubuntu/Debian
sudo apt install python3-poetry

# Fedora
sudo dnf install poetry

# Arch Linux
sudo pacman -S python-poetry
```

### Install System Dependencies

#### Ubuntu/Debian

```bash
# Install Playwright dependencies
sudo apt-get update
sudo apt-get install -y \
    libgbm-dev \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2

# Or use Playwright auto install
playwright install-deps
```

#### Fedora

```bash
sudo dnf install -y \
    nss \
    alsa-lib \
    at-spi2-atk \
    cups-libs \
    gtk3 \
    libdrm \
    libgbm \
    libxkbcommon \
    mesa-libgbm
```

#### Arch Linux

```bash
sudo pacman -S \
    nss \
    alsa-lib \
    at-spi2-core \
    cups \
    libdrm \
    libxkbcommon \
    mesa
```

### Platform Specific Notes

#### 1. Virtual Display Mode

Headless servers need virtual display:

```bash
# Install Xvfb
# Ubuntu/Debian
sudo apt-get install xvfb

# Fedora
sudo dnf install xorg-x11-server-Xvfb

# Arch Linux
sudo pacman -S xorg-server-xvfb

# Start service with virtual display mode
python launch_camoufox.py --virtual-display
```

#### 2. Headless Mode (Recommended)

```bash
# No X Server needed, completely background run
python launch_camoufox.py --headless
```

#### 3. Permission Issues

```bash
# Ensure current user has permission to access necessary directories
chmod -R 755 ~/AIstudioProxyAPI

# If binding privileged ports (<1024) is needed
sudo setcap 'cap_net_bind_service=+ep' $(which python3)
```

#### 4. Firewall Configuration

**Ubuntu/Debian (ufw)**:

```bash
sudo ufw allow 2048/tcp
sudo ufw allow 3120/tcp
sudo ufw reload
```

**Fedora/RHEL (firewalld)**:

```bash
sudo firewall-cmd --permanent --add-port=2048/tcp
sudo firewall-cmd --permanent --add-port=3120/tcp
sudo firewall-cmd --reload
```

**iptables**:

```bash
sudo iptables -A INPUT -p tcp --dport 2048 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 3120 -j ACCEPT
sudo iptables-save
```

#### 5. systemd Service (Resident Run)

Create `/etc/systemd/system/aistudio-proxy.service`:

```ini
[Unit]
Description=AI Studio Proxy API
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/AIstudioProxyAPI
Environment="PATH=/path/to/poetry/env/bin"
ExecStart=/path/to/poetry/env/bin/python launch_camoufox.py --headless
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable Service**:

```bash
sudo systemctl daemon-reload
sudo systemctl enable aistudio-proxy
sudo systemctl start aistudio-proxy
sudo systemctl status aistudio-proxy
```

#### 6. SELinux (Fedora/RHEL)

If SELinux is enabled:

```bash
# Temporarily set to permissive mode
sudo setenforce 0

# Or create custom policy
# (Requires SELinux management knowledge)
```

### Recommended Terminals

- **GNOME Terminal**: GNOME default
- **Konsole**: KDE Plasma default
- **tmux**: Terminal multiplexer, suitable for remote server
- **Terminator**: Supports split screen

### Common Issues

**Issue**: `libgbm.so.1: cannot open shared object file`

**Solution**:

```bash
sudo apt-get install libgbm1
# Or
sudo dnf install libgbm
```

**Issue**: Playwright browser installation failed

**Solution**:

```bash
# Use Playwright auto install dependencies
playwright install-deps

# Manually install browser
playwright install firefox
```

---

## Docker Environment

### Supported Platforms

- **x86_64**: Fully supported
- **ARM64**: Fully supported (Including Apple Silicon)

### Quick Start

```bash
cd docker
cp .env.docker .env
nano .env  # Edit config
docker compose up -d
```

### Platform Differences

#### Linux (Native)

- ✅ Best performance
- ✅ Fully supports all features
- ✅ Minimal resource usage

#### macOS (Docker Desktop)

- ✅ Supports all features
- ⚠️ Performance slightly lower than native Linux
- ⚠️ Higher resource usage (VM overhead)
- 💡 **Tip**: Allocate sufficient RAM and CPU

**Docker Desktop Config**:

- Memory: At least 4GB
- CPU: At least 2 Cores

#### Windows (Docker Desktop)

- ✅ Supports all features
- ⚠️ Requires WSL 2 backend
- ⚠️ Performance slightly lower than Linux
- 💡 **Tip**: Ensure WSL 2 is enabled

**WSL 2 Config**:

```bash
# Check WSL version
wsl --list --verbose

# If using WSL 1, upgrade to WSL 2
wsl --set-version Ubuntu 2
wsl --set-default-version 2
```

### Auth File Mounting

All platforms need to get auth file on host then mount:

```yaml
# docker-compose.yml
volumes:
  - ./auth_profiles:/app/auth_profiles
```

**Steps**:

1. Run debug mode on host to get auth.
2. Ensure `auth_profiles` directory (containing `active/` subdirectory) is correctly mounted to container.
3. Restart container.

---

## Performance Comparison

Performance varies across platforms, mainly depending on underlying architecture and virtualization overhead:

1.  **Linux (Native)**: Usually provides best performance and lowest latency, benefiting from `uvloop` support and efficient process management.
2.  **macOS**: Good performance, Apple Silicon chips perform excellently.
3.  **Windows**: Due to lack of `uvloop` support and file system differences, performance is slightly lower than Linux/macOS, but completely sufficient for daily use.
4.  **Docker**:
    - **Linux**: Performance close to native.
    - **macOS/Windows**: Due to Docker Desktop using VM, there is extra CPU and memory overhead, startup time and response latency might be slightly higher.

---

## Recommended Configuration

### Development Environment

- **Primary**: macOS or Linux (Native)
- **Alternative**: Windows 10/11 (Native)
- **Not Recommended**: Docker (Unless isolation needed)

### Production Environment

- **Primary**: Linux (Native or Docker)
- **Alternative**: Docker (Cross-platform deployment)
- **Not Recommended**: Windows Server (Performance and compatibility issues)

### Testing Environment

- **Primary**: Docker (Consistency)
- **Alternative**: Virtual Machine

---

## Related Documentation

- [Quick Start Guide](quick-start-guide.md) - Quick deployment
- [Installation Guide](installation-guide.md) - Detailed installation steps
- [Docker Deployment Guide](../docker/README-Docker.md) - Docker deployment
- [Troubleshooting Guide](troubleshooting.md) - Platform specific issues

---

If platform specific issues persist, please check Troubleshooting Guide or submit an Issue.
