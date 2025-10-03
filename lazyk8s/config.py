"""Configuration module for lazyk8s"""

import os
import logging
from pathlib import Path
from typing import Optional


class AppConfig:
    """Application configuration"""

    def __init__(self, debug: bool = False, kubeconfig: Optional[str] = None):
        """Initialize application configuration

        Args:
            debug: Enable debug logging
            kubeconfig: Path to kubeconfig file (uses default if None)
        """
        self.debug = debug
        self.log_level = "DEBUG" if debug else "INFO"

        # Setup logging
        self.logger = self._setup_logger()

        # Setup kubeconfig path
        if kubeconfig:
            self.kubeconfig = kubeconfig
        else:
            kubeconfig_env = os.getenv("KUBECONFIG")
            if kubeconfig_env:
                self.kubeconfig = kubeconfig_env
            else:
                home = Path.home()
                self.kubeconfig = str(home / ".kube" / "config")

    def _setup_logger(self) -> logging.Logger:
        """Setup application logger"""
        logger = logging.getLogger("lazyk8s")
        logger.setLevel(self.log_level)

        # Log to file instead of console to avoid interfering with TUI
        log_file = Path.home() / ".cache" / "lazyk8s" / "lazyk8s.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # File handler
        handler = logging.FileHandler(log_file)
        handler.setLevel(self.log_level)

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)

        logger.addHandler(handler)
        return logger
