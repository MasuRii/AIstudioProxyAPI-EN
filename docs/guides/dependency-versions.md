# Dependency Versions Guide

This document details the project's Python version requirements, Poetry dependency management, and version control strategy.

## 📦 Dependency Management Tool

> ⚠️ **Important Note**: This project's dependencies are entirely managed by **Poetry**. `pyproject.toml` and `poetry.lock` are the **Single Source of Truth** for dependency configuration. Please do not manually maintain `requirements.txt`.

The project uses **Poetry** for modern Python dependency management, offering advantages over traditional `requirements.txt`:

- ✅ **Dependency Resolution**: Automatically resolves version conflicts
- ✅ **Lock File**: `poetry.lock` ensures environment consistency
- ✅ **Virtual Environment**: Automatically creates and manages virtual environments
- ✅ **Dependency Groups**: Distinguishes between production and development dependencies
- ✅ **Semantic Versioning**: More precise version control
- ✅ **Build System**: Built-in packaging and publishing features

## 🐍 Python Version Requirements

### Poetry Configuration

```toml
[tool.poetry.dependencies]
python = ">=3.9,<4.0"
```

### Recommended Configuration

- **Production**: Python 3.10+ or 3.11+ (Best performance and stability)
- **Development**: Python 3.11+ or 3.12+ (Best development experience)
- **Minimum Requirement**: Python 3.9 (Basic feature support)

### Version Compatibility Matrix

| Python Version | Support Status | Recommendation | Key Features | Note |
| ---------- | ----------- | -------- | -------------- | -------------------------- |
| 3.8 | ❌ Not Supported | Not Recommended | - | Missing necessary type annotation features |
| 3.9 | ✅ Fully Supported | Usable | Basic Features | Minimum supported version, all features normal |
| 3.10 | ✅ Fully Supported | Recommended | Structured Pattern Matching | Docker default version, stable and reliable |
| 3.11 | ✅ Fully Supported | Highly Recommended | Performance Optimization | Significant performance boost, enhanced type hints |
| 3.12 | ✅ Fully Supported | Recommended | Faster Startup | Faster startup time, latest stable features |
| 3.13 | ✅ Fully Supported | Usable | Latest Features | Latest version, recommended for dev environment |

## 📋 Poetry Dependency Configuration

### pyproject.toml Structure

```toml
[tool.poetry]
name = "aistudioproxyapi"
version = "0.1.0"
package-mode = false

[tool.poetry.dependencies]
# Production dependencies
python = ">=3.9,<4.0"
fastapi = "==0.115.12"
# ... other dependencies

[tool.poetry.group.dev.dependencies]
# Development dependencies (Optional install)
pytest = "^7.0.0"
black = "^23.0.0"
# ... other development tools
```

### Version Constraint Syntax

Poetry uses semantic version constraints:

- `==1.2.3` - Exact version
- `^1.2.3` - Compatible version (>=1.2.3, <2.0.0)
- `~1.2.3` - Patch version (>=1.2.3, <1.3.0)
- `>=1.2.3,<2.0.0` - Version range
- `*` - Latest version

## 🔧 Core Dependency Versions

### Web Framework Related

```toml
fastapi = "==0.115.12"
pydantic = ">=2.7.1,<3.0.0"
uvicorn = "==0.29.0"
```

**Version Notes**:

- **FastAPI**: Uses latest stable version, includes performance optimizations and new features (like Query/Header/Cookie parameter model support).
- **Pydantic**: Modern data validation library, uses version range to ensure compatibility.
- **Uvicorn**: High-performance ASGI server.

### Browser Automation

```toml
playwright = "*"
camoufox = {version = "0.4.11", extras = ["geoip"]}
```

**Version Notes**:

- **Playwright**: Uses latest version (`*`) to ensure browser compatibility.
- **Camoufox**: Anti-fingerprinting browser, includes geoip data extension.

### Network and Security

```toml
aiohttp = "~=3.9.5"
requests = "==2.31.0"
cryptography = "==42.0.5"
pyjwt = "==2.8.0"
websockets = "==12.0"
aiosocks = "~=0.2.6"
python-socks = "~=2.7.1"
```

**Version Notes**:

- **aiohttp**: Async HTTP client, allows patch version updates.
- **cryptography**: Crypto library, fixed version ensures security.
- **websockets**: WebSocket support.
- **requests**: HTTP client library.

### System Tools

```toml
python-dotenv = "==1.0.1"
httptools = "==0.6.1"
uvloop = {version = "*", markers = "sys_platform != 'win32'"}
Flask = "==3.0.3"
tzdata = "^2025.2"
```

**Version Notes**:

- **uvloop**: Only installed on non-Windows systems, significantly improves performance.
- **httptools**: HTTP parsing optimization.
- **python-dotenv**: Environment variable management.
- **Flask**: Lightweight Web framework for specific features.
- **tzdata**: Timezone data support.

## 🔄 Poetry Dependency Management Commands

### Basic Commands

```bash
# Install all dependencies
poetry install

# Install including dev dependencies
poetry install --with dev

# Add new dependency
poetry add package_name

# Add dev dependency
poetry add --group dev package_name

# Remove dependency
poetry remove package_name

# Update dependencies
poetry update

# Update specific dependency
poetry update package_name

# View dependency tree
poetry show --tree

# Export requirements.txt (Only for build/compatibility, do not manually edit)
poetry export -f requirements.txt --output requirements.txt
```

### Lock File Management

```bash
# Update lock file
poetry lock

# Install without updating lock file
poetry install --no-update

# Check if lock file is up to date
poetry check
```

## 📊 Dependency Update Strategy

### Auto Update (Using ~ version range)

- `aiohttp~=3.9.5` - Allows patch version update (3.9.5 → 3.9.x)
- `aiosocks~=0.2.6` - Allows patch version update (0.2.6 → 0.2.x)
- `python-socks~=2.7.1` - Allows patch version update (2.7.1 → 2.7.x)

### Fixed Version (Using == exact version)

- Core framework components (FastAPI, Uvicorn, python-dotenv)
- Security related libraries (cryptography, pyjwt, requests)
- Components requiring high stability (websockets, httptools)

### Compatible Version (Using version range)

- `pydantic>=2.7.1,<3.0.0` - Compatible update within major version

### Latest Version (Using * or unlimited)

- `playwright = "*"` - Browser automation, needs latest features
- `uvloop = "*"` - Performance optimization library, continuous updates

## 💡 Upgrade Notes

- **Verification Testing**: After upgrading dependencies, be sure to run the full test suite in the development environment.
- **Breaking Changes**: Pay attention to version changelogs of major frameworks (like FastAPI, Pydantic) for potential breaking changes.
- **Security Updates**: Regularly check for security vulnerability updates in dependencies.

## Environment Specific Configuration

### Docker Environment

- **Base Image**: `python:3.10-slim-bookworm`
- **System Dependencies**: Automatically installs browser runtime dependencies
- **Python Version**: Fixed to 3.10 (Inside container)

### Development Environment

- **Recommended**: Python 3.11+
- **Virtual Environment**: Highly recommended to use venv or conda
- **IDE Support**: pyrightconfig.json configured (Python 3.13)

### Production Environment

- **Recommended**: Python 3.10 or 3.11
- **Stability**: Use fixed version dependencies
- **Monitoring**: Regularly check dependency security updates

## Troubleshooting

### Common Version Conflicts

1. **Python 3.8 Compatibility Issue**
   - Upgrade to Python 3.9+
   - Check type hint syntax compatibility

2. **Dependency Version Conflict**
   - Use virtual environment isolation
   - Clear pip cache: `pip cache purge`

3. **System Dependency Missing**
   - Linux: Install `xvfb` for virtual display
   - Run `playwright install-deps`

### Version Check Commands

```bash
# Check Python version
python --version

# Check installed package versions
pip list

# Check outdated packages
pip list --outdated

# Check specific package info
pip show fastapi
```
