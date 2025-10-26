# Agent Guidelines for aitools

## Build/Test Commands
- No standard test framework detected - check with maintainer before running tests
- Type checking: `mypy` (mypy.ini present in project root)
- No standard lint command found - verify before running linters
- Run single Python module: `python -m aidb.module_name` or `python src/aidb/module_name.py`

## Code Style

### Imports
- Absolute imports preferred: `from aidb.module import Class`
- Type hints from typing: `from typing import List, Dict, Optional, Literal, Final, Any, Tuple`
- Use Final for constants: `CONSTANT: Final = value`
- Third-party before local imports

### Types & Annotations
- Always use type hints for function parameters and returns
- Use Optional[T] for nullable types
- Use Literal for string enums: `operation: Literal['nop','rate','scene']`
- MongoDB ObjectIds as string in public APIs, ObjectId internally

### Naming
- Classes: PascalCase
- Functions/variables: snake_case
- Private members: _leading_underscore
- Constants: UPPER_SNAKE_CASE

### Error Handling
- Print errors to console: `print(f"Error: {message}")`
- Return None or empty collections on failure
- Use try/except for MongoDB operations, file I/O
- Validate ObjectId strings before conversion

### Comments
- Docstrings for all public classes/methods (Google style)
- Minimal inline comments - code should be self-documenting
