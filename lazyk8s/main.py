"""Main entry point for lazyk8s CLI"""

import sys
import argparse
from pathlib import Path

from .config import AppConfig
from .app import App
from . import __version__


def init_args():
    """Initialize argument parser"""
    parser = argparse.ArgumentParser( prog="lazyk8s",description="lazyk8s - The lazier way to manage Kubernetes")
    parser.add_argument("namespace",nargs="?",help="Initial namespace to select")
    parser.add_argument("-d", "--debug",action="store_true",help="Enable debug mode")
    parser.add_argument("-c", "--config",action="store_true",help="Print the default config")
    parser.add_argument("--kubeconfig", type=str, help="Path to kubeconfig file")
    parser.add_argument("-v", "--version",action="version",version=f"lazyk8s {__version__}")

    return parser

def cli() -> None:
    """Main CLI entry point"""
    parser = init_args()
    args = parser.parse_args()

    if args.config:
        print_config()
        sys.exit(0)

    # Create application configuration
    app_config = AppConfig(debug=args.debug, kubeconfig=args.kubeconfig)

    # Create and run application
    try:
        app = App(app_config, initial_namespace=args.namespace)
        app.run()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        if args.debug:
            raise
        print(f"Error: {e}")
        sys.exit(1)


def print_config() -> None:
    """Print default configuration"""
    import os
    home = Path.home()
    default_kubeconfig = home / ".kube" / "config"
    current_kubeconfig = os.getenv("KUBECONFIG", str(default_kubeconfig))

    print("lazyk8s Configuration")
    print("=" * 50)
    print(f"Default Kubeconfig: {default_kubeconfig}")
    print(f"Current Kubeconfig: {current_kubeconfig}")
    print(f"Debug Mode: False")
    print("=" * 50)


def main() -> None:
    """Main entry point"""
    cli()


if __name__ == "__main__":
    main()
