import logging
import os
import sys
from typing import Dict, List, Optional

from launcher.config import ACTIVE_AUTH_DIR, SAVED_AUTH_DIR

logger = logging.getLogger("CamoufoxLauncher")


def ensure_auth_dirs_exist() -> None:
    try:
        os.makedirs(ACTIVE_AUTH_DIR, exist_ok=True)
        logger.debug(f"Active auth directory ready: {ACTIVE_AUTH_DIR}")
        os.makedirs(SAVED_AUTH_DIR, exist_ok=True)
        logger.debug(f"Saved auth directory ready: {SAVED_AUTH_DIR}")
    except Exception as e:
        logger.error(f"Failed to create auth directories: {e}", exc_info=True)
        sys.exit(1)


def check_dependencies(
    launch_server: Optional[bool], DefaultAddons: Optional[bool]
) -> None:
    logger.debug("[Init] Step 1: Checking dependencies...")
    required_modules: Dict[str, str] = {}
    if launch_server is not None and DefaultAddons is not None:
        required_modules["camoufox"] = "camoufox (for server and addons)"
    elif launch_server is not None:
        required_modules["camoufox_server"] = "camoufox.server"
        logger.warning(
            "  'camoufox.server' imported, but 'camoufox.DefaultAddons' not imported. Addon exclusion functionality may be limited."
        )
    missing_py_modules: List[str] = []
    dependencies_ok = True
    if required_modules:
        for module_name, install_package_name in required_modules.items():
            try:
                __import__(module_name)
                logger.debug(f"Module '{module_name}' found.")
            except ImportError:
                logger.error(
                    f"  Module '{module_name}' (package: '{install_package_name}') not found."
                )
                missing_py_modules.append(install_package_name)
                dependencies_ok = False
    else:
        # Check if internal launch mode, if so camoufox must be importable
        is_any_internal_arg = any(arg.startswith("--internal-") for arg in sys.argv)
        if is_any_internal_arg and (launch_server is None or DefaultAddons is None):
            logger.error(
                "  Internal launch mode (--internal-*) requires 'camoufox' package, but failed to import."
            )
            dependencies_ok = False
        elif not is_any_internal_arg:
            logger.debug(
                "Internal launch mode not requested and camoufox.server not imported, skipping 'camoufox' Python package check."
            )

    try:
        from server import app as server_app_check

        if server_app_check:
            logger.debug("[Init] Successfully imported app object from server.py")
    except ImportError as e_import_server:
        logger.error(
            f"  Cannot import 'app' object from 'server.py': {e_import_server}",
            exc_info=True,
        )
        logger.error("Please ensure 'server.py' file exists and has no import errors.")
        dependencies_ok = False

    if not dependencies_ok:
        logger.error("-------------------------------------------------")
        logger.error("Dependency check failed!")
        if missing_py_modules:
            logger.error(f"Missing Python libraries: {', '.join(missing_py_modules)}")
            logger.error(
                f"   Please try installing with pip: pip install {' '.join(missing_py_modules)}"
            )
        logger.error("-------------------------------------------------")
        sys.exit(1)
    else:
        logger.debug("[Init] All dependency checks passed")
