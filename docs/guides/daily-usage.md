# Daily Usage Guide

This guide describes how to run the project daily after completing the initial authentication setup. The project offers multiple startup methods, with the simplified startup based on `.env` configuration file being recommended.

## Overview

After completing the initial authentication setup, you can choose the following ways for daily operation:

- **Command Line Start**: Directly use the [`launch_camoufox.py`](../launch_camoufox.py) command-line tool
- **Docker Deployment**: Use containerized deployment

## ⭐ Simplified Startup (Recommended)

**Unified configuration management based on `.env` file makes startup extremely simple!**

### Configuration Advantages

- ✅ **Configure Once, Benefit Forever**: After configuring the `.env` file, the startup command is extremely concise
- ✅ **Worry-free Updates**: Directly start after `git pull` without reconfiguration
- ✅ **Centralized Parameter Management**: All configuration items are unified in the `.env` file
- ✅ **Environment Isolation**: Different environments can use different configuration files

### Basic Startup (Recommended)

```bash
# Command line start (Recommended for daily use)
python launch_camoufox.py --headless

# Debug mode (For initial setup or troubleshooting)
python launch_camoufox.py --debug
```

**That's it!** All configurations are preset in the `.env` file, no complex command-line arguments needed.

## Launcher Description

### About `--virtual-display` (Linux Virtual Display Headless Mode)

- **Why use it?** Compared to standard headless mode, virtual display mode runs the browser by creating a complete virtual X server environment (Xvfb). This can simulate a more realistic desktop environment, potentially further reducing the risk of being detected as an automated script or bot, especially suitable for scenarios with higher anti-fingerprinting and anti-detection requirements, while ensuring the service runs normally in a desktop-less environment.
- **When to use it?** When you run under Linux environment and wish to operate in headless mode.
- **How to use it?**
  1. Ensure your Linux system has `xvfb` installed (see installation instructions in [Installation Guide](installation-guide.md)).
  2. Add `--virtual-display` flag when running [`launch_camoufox.py`](../launch_camoufox.py). For example:
     ```bash
     python launch_camoufox.py --virtual-display --server-port 2048 --stream-port 3120 --internal-camoufox-proxy ''
     ```

## Proxy Configuration Priority

The project adopts a unified proxy configuration management system, determining proxy settings in the following priority order:

1. **`--internal-camoufox-proxy` command line argument** (Highest priority)
   - Explicitly specify proxy: `--internal-camoufox-proxy 'http://127.0.0.1:7890'`
   - Explicitly disable proxy: `--internal-camoufox-proxy ''`
2. **`UNIFIED_PROXY_CONFIG` environment variable** (Recommended, configured in .env file)
3. **`HTTP_PROXY` environment variable**
4. **`HTTPS_PROXY` environment variable**
5. **System proxy settings** (gsettings under Linux, lowest priority)

**Recommended Configuration Method**:

```env
# Unified proxy configuration in .env file
UNIFIED_PROXY_CONFIG=http://127.0.0.1:7890
# Or disable proxy
UNIFIED_PROXY_CONFIG=
```

**Important Note**: This proxy configuration applies to both the Camoufox browser and the upstream connection of the streaming proxy service, ensuring consistent proxy behavior across the system.

## Three-Layer Response Acquisition Mechanism Configuration

The project adopts a three-layer response acquisition mechanism to ensure high availability and optimal performance. For details, please refer to [Streaming Modes Explained](streaming-modes.md).

### Mode 1: Prefer Integrated Streaming Proxy (Default Recommended)

**Using `.env` configuration (Recommended):**

```env
# Configure in .env file
STREAM_PORT=3120
UNIFIED_PROXY_CONFIG=http://127.0.0.1:7890  # If proxy is needed
```

```bash
# Then simple start
python launch_camoufox.py --headless
```

**Command line override (Advanced users):**

```bash
# Use custom streaming proxy port
python launch_camoufox.py --headless --stream-port 3125

# Enable proxy configuration
python launch_camoufox.py --headless --internal-camoufox-proxy 'http://127.0.0.1:7890'

# Explicitly disable proxy (Overrides setting in .env)
python launch_camoufox.py --headless --internal-camoufox-proxy ''
```

In this mode, the main server will prioritize attempting to get response via the integrated streaming proxy on port `3120` (or `STREAM_PORT` configured in `.env`). If it fails, it falls back to Playwright page interaction.

### Mode 2: Prefer External Helper Service (Disable Integrated Streaming Proxy)

**Using `.env` configuration (Recommended):**

```bash
# Configure in .env file
STREAM_PORT=0  # Disable integrated streaming proxy
GUI_DEFAULT_HELPER_ENDPOINT=http://your-helper-service.com/api/getStreamResponse

# Then simple start
python launch_camoufox.py --headless
```

**Command line override (Advanced users):**

```bash
# External Helper mode
python launch_camoufox.py --headless --stream-port 0 --helper 'http://your-helper-service.com/api/getStreamResponse'
```

In this mode, the main server will prioritize attempting to get response via the Helper endpoint (requires valid `auth_profiles/active/*.json` to extract `SAPISID`). If it fails, it falls back to Playwright page interaction.

### Mode 3: Use Playwright Page Interaction Only (Disable All Streaming Proxies and Helpers)

**Using `.env` configuration (Recommended):**

```bash
# Configure in .env file
STREAM_PORT=0  # Disable integrated streaming proxy
GUI_DEFAULT_HELPER_ENDPOINT=  # Disable Helper service

# Then simple start
python launch_camoufox.py --headless
```

**Command line override (Advanced users):**

```bash
# Pure Playwright mode
python launch_camoufox.py --headless --stream-port 0 --helper ''
```

In this mode, the main server will only get response by interacting with the AI Studio page via Playwright (simulating clicking "Edit" or "Copy" buttons). This is the traditional fallback method.

## GUI Launcher (Deprecated)

> [!WARNING]
> The GUI launcher (`gui_launcher.py`) has been moved to the `deprecated/` directory. It is recommended to use the command line method `python launch_camoufox.py`.

The project used to provide a Tkinter-based Graphical User Interface (GUI) launcher, but it is now deprecated.

The functions of this tool can be implemented via the following command line rewrites:

- **Headed Mode**: `python launch_camoufox.py --debug`
- **Headless Mode**: `python launch_camoufox.py --headless`

### Usage Recommendations

- **First Run**: Use `python launch_camoufox.py --debug` and manually complete login
- **Daily Background Run**: `python launch_camoufox.py --headless`
- **Troubleshooting**: Use `--debug` mode to observe browser behavior

## Important Considerations

### Configuration Priority

1. **`.env` file configuration** - Recommended configuration method, set once for long-term use
2. **Command line arguments** - Can override settings in `.env` file, suitable for temporary adjustment
3. **Environment variables** - Lowest priority, mainly used for system-level configuration

### Usage Recommendations

- **Daily Use**: After configuring the `.env` file, simply use `python launch_camoufox.py --headless`
- **Temporary Adjustment**: When temporary configuration modification is needed, use command line arguments to override without modifying the `.env` file
- **First Setup**: Recommended to use "Create New Auth Profile" function in GUI, or use `python launch_camoufox.py --debug` for manual setup

**Only when you confirm that everything runs normally using debug mode (especially login and auth saving inside the browser), and there is a valid auth file in the `auth_profiles/active/` directory, is it recommended to use headless mode as the standard way for daily background operation.**

## Next Steps

After daily run setup is complete, please refer to:

- [API Usage Guide](api-usage.md)
- [Web UI Guide](webui-guide.md)
- [Troubleshooting Guide](troubleshooting.md)
