# lazyk8s

The lazier way to manage Kubernetes - Python edition

A terminal UI for managing Kubernetes clusters with ease.

## Features

- Browse pods across namespaces
- View pod information and logs
- Execute shells in containers
- Colorized log output
- Keyboard-driven interface

## Installation

```bash
pip install lazyk8s
```

## Usage

```bash
lazyk8s
```

## Requirements

- Python 3.8+
- kubectl configured with access to your cluster
- KUBECONFIG environment variable set (or default ~/.kube/config)

## Development

```bash
pip install -e ".[dev]"
```

## Acknowledgements

- Inspired by [lazydocker](https://github.com/jesseduffield/lazydocker) by Jesse Duffield
- Built with [Textual](https://github.com/Textualize/textual) TUI framework
