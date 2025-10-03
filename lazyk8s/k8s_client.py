"""Kubernetes client wrapper for lazyk8s"""

import logging
from typing import List, Optional, Tuple
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream


class K8sClient:
    """Kubernetes client for interacting with clusters"""

    def __init__(self, kubeconfig_path: Optional[str] = None, logger: Optional[logging.Logger] = None):
        """Initialize Kubernetes client

        Args:
            kubeconfig_path: Path to kubeconfig file (uses default if None)
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.namespace = "default"
        self._namespace_list: List[str] = []

        # Load kubeconfig
        try:
            if kubeconfig_path:
                config.load_kube_config(config_file=kubeconfig_path)
            else:
                config.load_kube_config()
        except Exception as e:
            self.logger.error(f"Failed to load kubeconfig: {e}")
            raise

        # Initialize API clients
        self.core_v1 = client.CoreV1Api()
        self.api_client = client.ApiClient()

        # Load namespaces
        self._refresh_namespaces()

    def _refresh_namespaces(self) -> None:
        """Refresh the list of namespaces"""
        try:
            namespaces = self.core_v1.list_namespace()
            self._namespace_list = [ns.metadata.name for ns in namespaces.items]
        except ApiException as e:
            self.logger.error(f"Failed to list namespaces: {e}")
            raise

    def get_namespaces(self) -> List[str]:
        """Get list of all namespaces"""
        return self._namespace_list

    def get_current_namespace(self) -> str:
        """Get currently selected namespace"""
        return self.namespace

    def set_namespace(self, namespace: str) -> None:
        """Set the current namespace"""
        self.namespace = namespace

    def get_pods(self) -> List[client.V1Pod]:
        """Get all pods in current namespace"""
        try:
            pods = self.core_v1.list_namespaced_pod(self.namespace)
            return pods.items
        except ApiException as e:
            self.logger.error(f"Failed to list pods: {e}")
            return []

    def get_pod(self, name: str) -> Optional[client.V1Pod]:
        """Get a specific pod by name"""
        try:
            return self.core_v1.read_namespaced_pod(name, self.namespace)
        except ApiException as e:
            self.logger.error(f"Failed to get pod {name}: {e}")
            return None

    def get_pod_logs(self, pod_name: str, container_name: str, lines: int = 100) -> str:
        """Get logs from a pod container"""
        try:
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=self.namespace,
                container=container_name,
                tail_lines=lines
            )
            return logs
        except ApiException as e:
            self.logger.error(f"Failed to get logs for {pod_name}/{container_name}: {e}")
            return f"Error: {e}"

    def stream_pod_logs(self, pod_name: str, container_name: str) -> str:
        """Stream logs from a pod container (for future streaming implementation)"""
        try:
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=self.namespace,
                container=container_name,
                follow=False,
                tail_lines=100
            )
            return logs
        except ApiException as e:
            self.logger.error(f"Failed to stream logs: {e}")
            return f"Error: {e}"

    def exec_in_pod(self, pod_name: str, container_name: str, command: List[str]) -> str:
        """Execute a command in a pod container"""
        try:
            resp = stream(
                self.core_v1.connect_get_namespaced_pod_exec,
                pod_name,
                self.namespace,
                container=container_name,
                command=command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False
            )
            return resp
        except ApiException as e:
            self.logger.error(f"Failed to exec in pod: {e}")
            return f"Error: {e}"

    def get_pod_status(self, pod: client.V1Pod) -> str:
        """Get a human-readable pod status"""
        phase = pod.status.phase
        if pod.status.reason:
            phase = pod.status.reason

        restarts = 0
        ready = 0
        total = len(pod.status.container_statuses) if pod.status.container_statuses else 0

        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                restarts += cs.restart_count
                if cs.ready:
                    ready += 1
                if cs.state.waiting and cs.state.waiting.reason:
                    phase = cs.state.waiting.reason
                elif cs.state.terminated and cs.state.terminated.reason:
                    phase = cs.state.terminated.reason

        return f"{phase} ({ready}/{total}) Restarts:{restarts}"

    def get_container_names(self, pod: client.V1Pod) -> List[str]:
        """Get list of container names in a pod"""
        return [container.name for container in pod.spec.containers]

    def fuzzy_search_namespaces(self, search: str) -> List[str]:
        """Search namespaces with fuzzy matching"""
        if not search:
            return self._namespace_list

        search_lower = search.lower()
        return [ns for ns in self._namespace_list if search_lower in ns.lower()]

    def delete_pod(self, pod_name: str) -> bool:
        """Delete a pod"""
        try:
            self.core_v1.delete_namespaced_pod(pod_name, self.namespace)
            return True
        except ApiException as e:
            self.logger.error(f"Failed to delete pod {pod_name}: {e}")
            return False

    def delete_namespace(self, namespace_name: str) -> bool:
        """Delete a namespace"""
        try:
            self.core_v1.delete_namespace(namespace_name)
            return True
        except ApiException as e:
            self.logger.error(f"Failed to delete namespace {namespace_name}: {e}")
            return False

    def get_cluster_info(self) -> Tuple[str, str]:
        """Get cluster host and version information"""
        try:
            # Get configuration to extract host
            contexts, active_context = config.list_kube_config_contexts()
            if active_context:
                cluster_name = active_context['context']['cluster']
                host = cluster_name
            else:
                host = "unknown"

            # Get server version
            version_api = client.VersionApi()
            version_info = version_api.get_code()
            version = version_info.git_version

            return host, version
        except Exception as e:
            self.logger.error(f"Failed to get cluster info: {e}")
            return "unknown", "unknown"
