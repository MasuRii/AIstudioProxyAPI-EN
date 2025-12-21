# Contributing to AI Studio Proxy API

Thank you for your interest in contributing! We welcome bug reports, feature requests, and pull requests.

## Getting Started

### Fork & Clone

```bash
git clone https://github.com/YOUR_USERNAME/AIstudioProxyAPI.git
cd AIstudioProxyAPI
```

### Install Dependencies

```bash
# Install Poetry (if not already installed)
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install --with dev
```

### Run the Test Suite

```bash
poetry run pytest
```

## Making Changes

1. **Create a branch**: `git checkout -b feature/your-feature`
2. **Make your changes**
3. **Run checks** before committing:
   ```bash
   poetry run ruff check .
   poetry run ruff format .
   poetry run pyright
   poetry run pytest
   ```
4. **Commit** using [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` New feature
   - `fix:` Bug fix
   - `docs:` Documentation
   - `refactor:` Code restructuring
5. **Open a Pull Request**

## Code Style

We use:

- **Ruff** for linting and formatting
- **Pyright** for type checking
- **80% test coverage** minimum for modified files

See [Development Guide](docs/development-guide.md) for detailed coding conventions.

## Reporting Issues

Please include:

- Steps to reproduce
- Expected vs actual behavior
- Python version and OS
- Relevant logs (from `errors_py/` if available)

## Questions?

- Check [Troubleshooting Guide](docs/troubleshooting.md)
- Open a Discussion or Issue

## License

Contributions are licensed under [AGPLv3](LICENSE).
