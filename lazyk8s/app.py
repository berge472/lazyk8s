"""Application core for lazyk8s"""

from .config import AppConfig
from .k8s_client import K8sClient
from .gui import Gui


class App:
    """Main application class"""

    def __init__(self, app_config: AppConfig, initial_namespace: str = None):
        """Initialize the application

        Args:
            app_config: Application configuration
            initial_namespace: Optional initial namespace to select
        """
        self.config = app_config
        self.logger = app_config.logger

        # Initialize Kubernetes client
        self.k8s_client = K8sClient(
            kubeconfig_path=app_config.kubeconfig,
            logger=self.logger
        )

        # Set initial namespace if provided
        if initial_namespace:
            self.k8s_client.set_namespace(initial_namespace)

        # Initialize GUI
        self.gui = Gui(self.k8s_client, app_config)

    def run(self) -> None:
        """Run the application"""
        try:
            self.gui.run()
        except KeyboardInterrupt:
            self.logger.info("Application interrupted by user")
        except Exception as e:
            self.logger.error(f"Application error: {e}")
            raise
