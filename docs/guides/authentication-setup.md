# First Run & Authentication Setup Guide

To avoid manually logging into AI Studio every time you start, you need to run in [`launch_camoufox.py --debug`](../launch_camoufox.py) mode once to generate an authentication file.

## Importance of Authentication File

**The authentication file is key to headless mode**: Headless mode relies on a valid `.json` file in the `auth_profiles/active/` directory to maintain login state and access permissions. **Files may expire**, requiring periodic manual runs of [`launch_camoufox.py --debug`](../launch_camoufox.py) mode to login and save a new authentication file for replacement.

### 🐳 Special Note for Docker Users

**Docker containers typically run in headless mode and cannot support direct interactive login.**

1.  Please ensure you generate the authentication file on the **host machine** (your Windows/Mac/Linux computer) following this guide first.
2.  Ensure the generated `.json` file is placed in the `auth_profiles/active/` directory on the host machine.
3.  When starting the Docker container, this directory will be mounted, allowing the container to read the authentication information.

## Method 1: Run Debug Mode via Command Line

**Recommended configuration using .env**:

```env
# .env file configuration
DEFAULT_FASTAPI_PORT=2048
STREAM_PORT=0
LAUNCH_MODE=normal
DEBUG_LOGS_ENABLED=true

# [IMPORTANT] Must be set to true to save auth profiles!
AUTO_SAVE_AUTH=true
```

> [!WARNING]
> `AUTO_SAVE_AUTH=true` is required to save the authentication profile. If set to `false` (default), the authentication state will not be saved after a successful login.

```bash
# Simplified start command (Recommended)
python launch_camoufox.py --debug

# Traditional command line way (Still supported)
python launch_camoufox.py --debug --server-port 2048 --stream-port 0 --helper '' --internal-camoufox-proxy ''
```

**Important Parameters:**

- `--debug`: Starts in headed mode, used for first-time authentication and debugging.
- `--server-port <port>`: Specifies the port for the FastAPI server (Default: 2048).
- `--stream-port <port>`: Starts the integrated streaming proxy service port (Default: 3120). Set to `0` to disable this service; recommended to disable for first run.
- `--helper <endpoint_url>`: Specifies the address of an external Helper service. Set to empty string `''` to not use external Helper.
- `--internal-camoufox-proxy <proxy_address>`: Specifies a proxy for the Camoufox browser. Set to empty string `''` to not use a proxy.
- **Note**: If enabling the streaming proxy service, it is recommended to also configure the `--internal-camoufox-proxy` parameter to ensure normal operation.

### Operational Steps

1.  After running the script, the program will ask: `Do you want to create and save a new auth profile? (y/n)`.
    - Input `y` and Enter: Follow prompts to enter a filename (e.g., `my-auth`), it will save automatically after successful login.
    - Input `n` or just Enter: It will ask whether to save after login ends.
2.  The script starts Camoufox, and you will see a **Firefox browser window with UI** pop up.
3.  **Key Interaction:** **Complete Google Login in the popped-up browser window** until you see the AI Studio chat interface. (The script handles browser connection automatically, no manual user operation needed there).
4.  **Login Confirmation:** When the system detects the login page and displays a prompt in the terminal like:
    ```
    Login page detected. Please complete Google login in the browser window, then press Enter here to continue...
    ```
    **You must press the Enter key in the terminal to confirm the operation to proceed**. This confirmation step is mandatory; the system waits for user confirmation before checking login status.
5.  **Save File**:
    - If you chose auto-save in Step 1, the system automatically saves the file to `auth_profiles/saved/`.
    - If you chose not to auto-save in Step 1, the terminal will prompt `Do you want to save the current browser auth state to a file? (y/N)`, input `y` and follow instructions.
6.  **Activate File**: **Move the newly generated `.json` file from `auth_profiles/saved/` to the `auth_profiles/active/` directory.** Ensure there is only one `.json` file in the `active` directory.
7.  You can press `Ctrl+C` to stop the `--debug` mode execution.

## Method 2: Start Headed Mode via GUI (Deprecated)

> [!WARNING]
> The GUI launcher (`gui_launcher.py`) has been moved to the `deprecated/` directory. Please use the command line method above.

The following steps are for reference only and are no longer recommended:

1.  Run `python deprecated/gui_launcher.py`.
2.  In the "Auth Profile Management" area, click the **"Manage Profiles"** button.
3.  In the popup window, click the **"Create New Profile"** button.
4.  Enter the desired filename (e.g., `account1`) and click OK.
5.  Complete Google Login in the popped-up browser window.
6.  After successful login, the auth file is automatically saved to the `auth_profiles/saved/` directory.
7.  Back in the GUI main interface, click **"Manage Profiles"** again.
8.  Select the file created just now from the list and click **"Activate Selected"**. This automatically moves it to the `active` directory.

## Activating Auth File

1. Go to the `auth_profiles/saved/` directory and find the `.json` auth file you just saved.
2. **Move or Copy** this `.json` file to the `auth_profiles/active/` directory.
3. **Important:** Ensure there is **exactly one `.json` file** in the `auth_profiles/active/` directory. Headless mode automatically loads the first `.json` file in this directory.

## Handling Auth File Expiration

**Auth files expire!** Google login status is not permanent. When headless mode fails to start and reports an authentication error or redirects to the login page, it means the auth file in the `active` directory is invalid. You need to:

1. Delete the old file in the `active` directory.
2. Re-execute the **[Method 1: Run Debug Mode via Command Line]** steps above to generate a new auth file.
3. Move the newly generated `.json` file to the `active` directory again.

## Important Note

- **Performance on First Access to New Host**: When accessing a new HTTPS host via the streaming proxy for the first time, the service needs to dynamically generate and sign a new child certificate for that host. This process can be time-consuming, causing the response to the first connection request for that new host to be slow, potentially even being misjudged as a browser load timeout by the main program (like the Playwright interaction logic in [`server.py`](../server.py)). Once the certificate is generated and cached, subsequent accesses to the same host will be significantly faster.

## Next Steps

After auth setup is complete, please refer to:

- [Daily Usage Guide](daily-usage.md)
- [API Usage Guide](api-usage.md)
- [Web UI Guide](webui-guide.md)
