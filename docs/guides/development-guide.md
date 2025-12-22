# Developer Guide

This document is intended for developers who wish to participate in project development, contribute code, or deeply customize features.

## 🛠️ Development Environment Setup

### Prerequisites

- **Python**: ≥3.9, <4.0 (Recommended 3.10+)
- **Poetry**: Dependency management tool
- **Node.js**: ≥18 (For frontend development, optional)
- **Git**: Version control

> **Tip**: If not doing frontend development, you can use `--skip-frontend-build` or set `SKIP_FRONTEND_BUILD=1` to skip frontend build.

### Quick Start

```bash
# Clone project
git clone https://github.com/CJackHwang/AIstudioProxyAPI.git
cd AIstudioProxyAPI

# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies (including dev dependencies)
poetry install --with dev

# Activate virtual environment
poetry shell
```

---

## 📁 Project Structure

> For detailed architecture description, see [Project Architecture Guide](architecture-guide.md)

```
AIstudioProxyAPI/
├── api_utils/              # FastAPI application core
│   ├── app.py             # Application entry
│   ├── routers/           # API routers (chat, health, models, etc.)
│   ├── request_processor.py
│   └── queue_worker.py
├── browser_utils/          # Browser automation
│   ├── page_controller.py
│   ├── page_controller_modules/  # Mixin submodules
│   ├── initialization/    # Initialization module
│   └── operations_modules/ # Operation submodules
├── launcher/               # Launcher module
├── config/                 # Configuration management
├── models/                 # Data models
├── stream/                 # Streaming proxy
├── logging_utils/          # Logging tools
├── tests/                  # Test directory
├── pyproject.toml         # Poetry configuration
└── pyrightconfig.json     # Pyright configuration
```

---

## 🔧 Dependency Management (Poetry)

### Common Commands

```bash
# View dependency tree
poetry show --tree

# Add dependency
poetry add package_name
poetry add --group dev package_name  # Dev dependency

# Update dependencies
poetry update

# Export requirements.txt
poetry export -f requirements.txt --output requirements.txt
```

### Virtual Environment

```bash
# View environment info
poetry env info

# Activate environment
poetry shell

# Run command
poetry run python script.py
```

---

## 🎨 Frontend Development (React)

Frontend is built using React + Vite + TypeScript.

### Development Mode

```bash
cd static/frontend

# Install dependencies
npm install

# Development server (Hot Reload)
npm run dev

# Build production version
npm run build

# Run tests
npm run test
```

### Skip Frontend Build

If only doing backend development, you can skip frontend build:

```bash
# Command line method
python -m launcher.runner --skip-frontend-build

# Environment variable method
SKIP_FRONTEND_BUILD=1 python -m launcher.runner
```

### Configuration Files

| File | Usage |
| ---------------------------------- | --------------- |
| `static/frontend/package.json` | Dependencies and scripts config |
| `static/frontend/vite.config.ts` | Vite build config |
| `static/frontend/tsconfig.json` | TypeScript config |
| `static/frontend/vitest.config.ts` | Vitest test config |

---

## 🔍 Type Checking (Pyright)

The project uses Pyright for type checking.

### Run Check

```bash
# Check entire project
pyright

# Check specific file
pyright api_utils/app.py

# Watch mode
pyright --watch
```

### Configuration

`pyrightconfig.json`:

```json
{
  "pythonVersion": "3.13",
  "typeCheckingMode": "off",
  "extraPaths": ["./api_utils", "./browser_utils", "./config", ...]
}
```

---

## 🧪 Testing

### ⚠️ Anti-Hang Protocol

The project strictly enforces anti-hang protocol:

1. **Forced Timeout**: Global `timeout = 120` (in `pyproject.toml`)
2. **Resource Cleanup**: Fixtures must close resources after `yield`
3. **Async Safety**: Forbid swallowing `asyncio.CancelledError`

### Run Tests

```bash
# Run all tests
poetry run pytest

# Run specific test
poetry run pytest tests/test_api.py

# Coverage report
poetry run pytest --cov=api_utils --cov-report=html
```

---

## 🔄 Development Workflow

### 1. Code Formatting

```bash
# Ruff format and Lint
poetry run ruff check .
poetry run ruff format .
```

### 2. Type Checking

```bash
pyright
```

### 3. Run Tests

```bash
poetry run pytest
```

### 4. Commit Code

```bash
git add .
git commit -m "feat: Add new feature"
git push origin feature-branch
```

---

## 📝 Code Standards

### Naming Conventions

| Type | Convention | Example |
| ------ | ------------ | ---------------------- |
| File Name | `snake_case` | `request_processor.py` |
| Class Name | `PascalCase` | `QueueManager` |
| Function Name | `snake_case` | `process_request` |
| Constant | `UPPER_CASE` | `DEFAULT_PORT` |

### Docstrings

```python
def process_request(request: ChatRequest) -> ChatResponse:
    """
    Process chat request

    Args:
        request: Chat request object

    Returns:
        ChatResponse: Chat response object

    Raises:
        ValidationError: When request data is invalid
    """
    pass
```

---

## 🧭 New Endpoint Standards

1. Create corresponding module under `api_utils/routers/`
2. Re-export in `api_utils/routers/__init__.py`
3. Use `api_utils.error_utils` to construct errors
4. Use `config.get_environment_variable` for environment variables

### Error Code Standards

| Error Code | Scenario |
| ------ | -------------------- |
| 499 | Client disconnected/cancelled |
| 502 | Upstream/Playwright failed |
| 503 | Service unavailable |
| 504 | Processing timeout |

---

## 🤝 Contribution Guide

### Submit Pull Request

1. Fork the project
2. Create branch: `git checkout -b feature/amazing-feature`
3. Commit: `git commit -m 'feat: Add feature'`
4. Push: `git push origin feature/amazing-feature`
5. Create Pull Request

### Code Review Checklist

- [ ] Code follows project standards
- [ ] Added necessary tests
- [ ] Tests passed
- [ ] Type check passed
- [ ] Documentation updated

---

## 🔗 Related Resources

- [Poetry Documentation](https://python-poetry.org/docs/)
- [Pyright Documentation](https://github.com/microsoft/pyright)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Playwright Documentation](https://playwright.dev/python/)
