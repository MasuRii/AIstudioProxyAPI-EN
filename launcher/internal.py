import os
import sys
import traceback

from launcher.config import determine_proxy_configuration


def run_internal_camoufox(args, launch_server, DefaultAddons):
    if not launch_server or not DefaultAddons:
        print(
            "Fatal Error (--internal-launch-mode): camoufox.server.launch_server or camoufox.DefaultAddons not available.",
            file=sys.stderr,
        )
        sys.exit(1)

    internal_mode_arg = args.internal_launch_mode
    auth_file = args.internal_auth_file
    camoufox_port_internal = args.internal_camoufox_port
    
    proxy_config = determine_proxy_configuration(args.internal_camoufox_proxy)
    actual_proxy_to_use = proxy_config["camoufox_proxy"]
    print(f"--- [Internal Camoufox Start] Proxy Config: {proxy_config['source']} ---", flush=True)

    camoufox_proxy_internal = actual_proxy_to_use
    camoufox_os_internal = args.internal_camoufox_os

    print(
        f"--- [Internal Camoufox Start] Mode: {internal_mode_arg}, Auth: {os.path.basename(auth_file) if auth_file else 'None'}, "
        f"Port: {camoufox_port_internal}, Proxy: {camoufox_proxy_internal or 'None'}, OS: {camoufox_os_internal} ---",
        flush=True,
    )

    try:
        launch_args_for_internal_camoufox = {
            "port": camoufox_port_internal,
            "addons": [],
            "exclude_addons": [DefaultAddons.UBO],
            "window": (1440, 900),
        }

        if camoufox_proxy_internal:
            launch_args_for_internal_camoufox["proxy"] = {
                "server": camoufox_proxy_internal
            }
        
        if auth_file:
            launch_args_for_internal_camoufox["storage_state"] = auth_file

        if "," in camoufox_os_internal:
            camoufox_os_list_internal = [
                s.strip().lower() for s in camoufox_os_internal.split(",")
            ]
            valid_os_values = ["windows", "macos", "linux"]
            if not all(val in valid_os_values for val in camoufox_os_list_internal):
                print(
                    f"Internal Camoufox Error: Invalid OS values: {camoufox_os_list_internal}",
                    file=sys.stderr,
                )
                sys.exit(1)
            launch_args_for_internal_camoufox["os"] = camoufox_os_list_internal
        elif camoufox_os_internal.lower() in ["windows", "macos", "linux"]:
            launch_args_for_internal_camoufox["os"] = camoufox_os_internal.lower()
        elif camoufox_os_internal.lower() != "random":
            print(
                f"Internal Camoufox Error: Invalid OS value: '{camoufox_os_internal}'",
                file=sys.stderr,
            )
            sys.exit(1)

        print(
            f"Parameters passed to launch_server: {launch_args_for_internal_camoufox}",
            flush=True,
        )

        if internal_mode_arg == "headless":
            launch_server(headless=True, **launch_args_for_internal_camoufox)
        elif internal_mode_arg == "virtual_headless":
            launch_server(headless="virtual", **launch_args_for_internal_camoufox)
        elif internal_mode_arg == "debug":
            launch_server(headless=False, **launch_args_for_internal_camoufox)

        print(
            f"--- [Internal Camoufox Start] launch_server ({internal_mode_arg} mode) call completed/blocked. ---",
            flush=True,
        )
    except Exception as e_internal_launch_final:
        print(
            f"Error (--internal-launch-mode): Exception in launch_server: {e_internal_launch_final}",
            file=sys.stderr,
            flush=True,
        )
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    sys.exit(0)
