# Contributing to Robin

Thank you for your interest in contributing to Robin! This document provides
guidelines and instructions for contributing.

## Code of Conduct

This project adheres to our [Code of Conduct](CODE_OF_CONDUCT.md). By participating,
you are expected to uphold this code.

## How to Contribute

### Reporting Bugs

1. Check existing issues to avoid duplicates
2. Use the bug report template when creating a new issue
3. Include steps to reproduce, expected behavior, and actual behavior
4. Include your Python version and OS

### Suggesting Enhancements

1. Check existing issues and discussions first
2. Use the feature request template
3. Describe the problem you're trying to solve

### Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes following our coding standards
4. Write or update tests as needed
5. Run the test suite: `pytest`
6. Run the linter: `ruff check .`
7. Commit with clear messages: `git commit -m "feat: your feature description"`
8. Push and create a Pull Request

### Commit Message Format

We follow conventional commits:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

### Coding Standards

- Follow PEP 8 for Python code
- Use type hints where possible
- Write docstrings for public functions
- Keep functions focused and small
- Write tests for new functionality
- Line length: 100 characters max

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/robin.git
cd robin

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .

# Run formatter
black .
```

## Project Structure

```
robin/
├── lib/           # Core modules (200+ Python files)
├── kait/          # CLI interface
├── adapters/      # Input integrations
├── config/        # Configuration templates
├── tests/         # Test suite (120+ test files)
├── docs/          # Documentation
├── scripts/       # Utility scripts
├── hooks/         # Integration hooks
├── templates/     # Template files
└── .github/       # CI/CD workflows
```

## Review Process

1. All PRs require at least one review
2. CI checks must pass
3. Code coverage should not decrease
4. Documentation must be updated if applicable

## Getting Help

- Open a [Discussion](https://github.com/blerbz/robin/discussions) for questions
- Check the [Documentation](docs/) for guides
- Look at existing tests for usage examples

## Recognition

All contributors are valued! We maintain a contributors list and highlight
significant contributions in release notes.

Thank you for helping make Robin better!

— The BLERBZ Team
