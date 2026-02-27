# Contributing to fluxer.py

Thanks for helping improve `fluxer.py`. This project aims to stay as close as possible to the public `discord.py` API while targeting Fluxer’s capabilities.

## Ground Rules

- Be respectful and constructive.
- No secrets or tokens in issues, PRs, or examples.
- Keep compatibility with `discord.py` semantics unless Fluxer requires a deviation.

## How to Contribute

1. **Open an issue first** for significant changes.
2. **Small fixes** can go straight to a PR.
3. Keep changes **focused** and avoid unrelated refactors.

## Development Setup

```bash
pip install -e .
pip install -e .[dev]
```

## Running Checks

```bash
python -m py_compile fluxer/*.py
python -m py_compile fluxer/ext/**/*.py
```

## API Coverage Updates

If Fluxer docs change, regenerate endpoints:

```bash
python fluxer/scripts/generate_api.py
```

## Style Guidelines

- Prefer clear, explicit names over cleverness.
- Keep public APIs aligned to `discord.py` naming where possible.
- Document any divergence in `fluxer/DOCS.md`.

## Tests

There is no formal test suite yet. If you add new functionality, include small example usage or add lightweight tests in a follow-up PR.

## Review Criteria

PRs are evaluated on:

- API parity with `discord.py`
- Correctness against Fluxer REST/Gateway behavior
- Minimal breaking changes
- Documentation updates for new features
