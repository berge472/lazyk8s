"""Main entry point for lazyk8s CLI"""

import sys
import click
from pathlib import Path

from .config import AppConfig
from .app import App


DEFAULT_VERSION = "0.1.0"


@click.command()
@click.option(
    "-d", "--debug",
    is_flag=True,
    help="Enable debug mode"
)
@click.option(
    "-c", "--config",
    is_flag=True,
    help="Print the default config"
)
@click.option(
    "--kubeconfig",
    type=click.Path(exists=True),
    help="Path to kubeconfig file"
)
@click.version_option(version=DEFAULT_VERSION, prog_name="lazyk8s")
def cli(debug: bool, config: bool, kubeconfig: str) -> None:
    """lazyk8s - The lazier way to manage Kubernetes

    A terminal UI for managing Kubernetes clusters with ease.
    """
    if config:
        print_config()
        sys.exit(0)

    # Create application configuration
    app_config = AppConfig(debug=debug, kubeconfig=kubeconfig)

    # Create and run application
    try:
        app = App(app_config)
        app.run()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        if debug:
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
