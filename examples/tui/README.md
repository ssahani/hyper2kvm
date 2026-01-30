# TUI (Text User Interface) Examples

This directory contains examples demonstrating the interactive TUI dashboard and progress bars.

## Available Examples

- **`tui_demo.py`** - Basic TUI demonstration with orange theme
  ```bash
  python tui_demo.py
  ```

- **`tui_dashboard_example.py`** - Complete dashboard example with VM monitoring
  ```bash
  python tui_dashboard_example.py
  ```

- **`tui_integration_example.py`** - Integration with migration workflows
  ```bash
  python tui_integration_example.py
  ```

- **`progress_bar_demo.py`** - Custom progress bar demonstrations
  ```bash
  python progress_bar_demo.py
  ```

## Features

- Orange-themed interface (customizable)
- Real-time progress tracking
- VM status monitoring
- 3-tier fallback for compatibility (rich → simple → basic)
- Custom progress bars with time estimates

## Requirements

For full TUI experience:
```bash
pip install 'hyper2kvm[tui]'
```

The TUI works with fallback on RHEL 10 even without optional dependencies.

## Documentation

- [docs/TUI_DASHBOARD.md](../../docs/TUI_DASHBOARD.md) - TUI usage guide
- [docs/TUI_IMPLEMENTATION.md](../../docs/TUI_IMPLEMENTATION.md) - Technical implementation
- [docs/ORANGE_THEME.md](../../docs/ORANGE_THEME.md) - Theme customization
