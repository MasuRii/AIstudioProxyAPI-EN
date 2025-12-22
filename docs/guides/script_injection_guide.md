# Tampermonkey Script Dynamic Injection Guide

## Overview

This feature allows you to dynamically mount Tampermonkey scripts to enhance AI Studio's model list, supporting custom model injection and configuration management. The system uses Playwright native network interception technology to parse the model list directly from the Tampermonkey script, ensuring 100% reliability and frontend-backend data consistency.

## Features

- ✅ **Playwright Native Interception** - Uses Playwright route interception, unaffected by browser security policies
- ✅ **Double Assurance Mechanism** - Network interception + Script injection, ensuring failsafe operation
- ✅ **Direct Script Parsing** - Automatically parses model lists from the Tampermonkey script, no extra config file needed
- ✅ **Frontend-Backend Sync** - Frontend and backend use the same model data source
- ✅ **Auto Adaptation** - Automatically fetches new model lists when the script updates
- ✅ **Silent Failure** - Silently skips if the script file does not exist, without affecting main functions

## Configuration

### Environment Variables

Add the following configuration to your `.env` file:

```bash
# Whether to enable script injection feature
ENABLE_SCRIPT_INJECTION=true

# Tampermonkey script file path (relative to project root)
# Model data is parsed directly from this script file
USERSCRIPT_PATH=browser_utils/more_models.js
```

## How It Works

```
Tampermonkey Script → Playwright Network Interception (Backend) + Script Injection (Frontend) → API Sync
```

1.  **Backend (Playwright)**: Intercepts `/api/models` requests at the network layer, directly injecting parsed model data. This is the core mechanism ensuring reliability.
2.  **Frontend (Browser)**: Auxiliarily injects the original Tampermonkey script into the page to ensure UI consistency.
3.  **Sync**: Frontend and backend use the same script data source, keeping completely consistent.

### Core Advantages

- 🎯 **High Reliability** - Unaffected by browser security restrictions
- ⚡ **Earlier Interception** - Intercepts at network level, superior to JavaScript injection
- 🛡️ **Double Assurance** - Network interception + Script injection
- 🔄 **Single Data Source** - Tampermonkey script is the sole source of model definitions

## Usage

### 1. Enable Script Injection

Ensure set in `.env` file:

```bash
ENABLE_SCRIPT_INJECTION=true
```

### 2. Prepare Script File

Place your Tampermonkey script at `browser_utils/more_models.js` (or the path you specified in `USERSCRIPT_PATH`).

**⚠️ The script file must exist, otherwise no injection operation will be performed.**

### 3. Start Service

Start AI Studio Proxy service normally, the system will automatically handle injection and parsing.

### 4. Verify Injection Effect

- **Frontend**: Injected models can be seen on the AI Studio page
- **API**: Full list containing injected models can be obtained via `/v1/models` endpoint

## Log Output Example

After enabling script injection, you will see output similar to this in the logs:

```
# Network interception related logs
Setting up network interception and script injection...
Successfully set up model list network interception
Successfully parsed 6 models from Tampermonkey script

# Logs during model list response processing
Captured potential model list response from: https://alkalimakersuite.googleapis.com/...
Added 6 injected models to API model list
Successfully parsed and updated model list. Total models parsed: 12

# Example of parsed models
👑 Kingfall (Script v1.6)
✨ Gemini 1.5 Pro (Script v1.6)
🦁 Goldmane (Script v1.6)
```

## Troubleshooting

### Script Injection Failed

1.  **Check File Path** - Ensure `USERSCRIPT_PATH` points to an existing file
2.  **Check File Permissions** - Ensure script file is readable
3.  **Check Logs** - Check detailed error messages

### Model Parsing Failed

1.  **Script Format** - Ensure `MODELS_TO_INJECT` array format in Tampermonkey script is correct
2.  **Required Fields** - Ensure each model has `name` and `displayName` fields
3.  **JavaScript Syntax** - Ensure script file is valid JavaScript format

### Disable Script Injection

If you encounter issues, you can temporarily disable script injection:

```bash
ENABLE_SCRIPT_INJECTION=false
```

## Advanced Usage

### Custom Script Path

You can use a different script file:

```bash
USERSCRIPT_PATH=custom_scripts/my_script.js
```

### Version Management

The system automatically parses version information in the script, maintaining consistent display effects with the Tampermonkey script, including emojis and version identifiers.

## Notes

1.  **Restart to Take Effect** - Service restart is needed after script file update
2.  **Browser Cache** - If model list doesn't update, try refreshing page or clearing browser cache
3.  **Compatibility** - Ensure your Tampermonkey script is compatible with current AI Studio page structure

## Technical Details

- **Core Implementation** - `browser_utils/initialization/network.py` implements Playwright network interception logic.
- **Script Injection** - `browser_utils/initialization/scripts.py` is responsible for injecting script into browser context.
- **Script Management** - `browser_utils/script_manager.py` is responsible for loading and parsing script content.
- **Script Parsing** - `browser_utils/operations_modules/parsers.py` is responsible for extracting model data from the script.
