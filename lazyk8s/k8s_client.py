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

    def get_pod_logs_all_containers(self, pod_name: str, container_names: List[str], lines: int = 100) -> str:
        """Get logs from multiple containers with prefixes, interlaced by timestamp"""
        try:
            import subprocess

            # Fetch logs from each container separately and combine them
            all_logs = []

            for container_name in container_names:
                # Run kubectl to get logs for this container with prefix
                cmd = [
                    "kubectl", "logs",
                    "-n", self.namespace,
                    pod_name,
                    "-c", container_name,
                    "--prefix=true",
                    "--timestamps=true",
                    f"--tail={lines}",
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0 and result.stdout.strip():
                    all_logs.append(result.stdout)
                elif result.returncode != 0:
                    self.logger.error(f"Failed to get logs for {container_name}: {result.stderr}")

            if not all_logs:
                return ""

            # Combine all logs and sort by timestamp
            combined_lines = []
            for log_output in all_logs:
                combined_lines.extend(log_output.strip().split("\n"))

            # Sort by timestamp (format: [pod/container] timestamp message)
            def extract_timestamp(line):
                try:
                    # Extract timestamp from format: [pod/container] 2024-01-15T10:30:45.123456789Z message
                    if "]" in line:
                        after_bracket = line.split("]", 1)[1].strip()
                        if " " in after_bracket:
                            timestamp_str = after_bracket.split(" ", 1)[0]
                            return timestamp_str
                except Exception:
                    pass
                return ""

            # Sort lines by timestamp
            sorted_lines = sorted(combined_lines, key=extract_timestamp)

            return "\n".join(sorted_lines)

        except Exception as e:
            self.logger.error(f"Failed to get combined logs: {e}")
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
        """Get cluster name and host information"""
        try:
            # Get configuration to extract cluster name and server
            contexts, active_context = config.list_kube_config_contexts()
            if active_context:
                cluster_name = active_context['context']['cluster']
                # Get the API server host from the kubernetes client configuration
                cfg = client.Configuration.get_default_copy()
                server = cfg.host if cfg.host else "unknown"
                host = f"{cluster_name} ({server})"
            else:
                host = "unknown"

            return host, ""
        except Exception as e:
            self.logger.error(f"Failed to get cluster info: {e}")
            return "unknown", ""

    def get_pod_events(self, pod_name: str) -> str:
        """Get events for a specific pod using kubectl describe format"""
        try:
            import subprocess

            # Use kubectl describe to get events in the same format as VSCode extension
            cmd = [
                "kubectl", "describe", "pod",
                "-n", self.namespace,
                pod_name
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                # Extract just the Events section from the describe output
                output = result.stdout

                # Find the Events section
                if "Events:" in output:
                    # Split at Events: and take everything after
                    events_section = output.split("Events:", 1)[1]

                    # Check if events show <none> - strip whitespace first
                    events_trimmed = events_section.strip()
                    if not events_trimmed or events_trimmed.lower().startswith("<none>"):
                        return ""

                    # The events section goes until the end
                    lines = events_section.split("\n")
                    event_lines = []
                    for line in lines:
                        # Keep lines that are part of the events table
                        stripped = line.strip()
                        if stripped and stripped.lower() != "<none>":
                            event_lines.append(line)

                    if not event_lines:
                        return ""

                    return "\n".join(event_lines)
                else:
                    return ""
            else:
                self.logger.error(f"Failed to get events: {result.stderr}")
                return ""

        except Exception as e:
            self.logger.error(f"Failed to get events: {e}")
            return ""

    def get_contexts(self) -> Tuple[List[dict], dict]:
        """Get all kubeconfig contexts and the current context"""
        try:
            contexts, active_context = config.list_kube_config_contexts()
            return contexts or [], active_context
        except Exception as e:
            self.logger.error(f"Failed to get contexts: {e}")
            return [], {}

    def switch_context(self, context_name: str) -> bool:
        """Switch to a different kubeconfig context"""
        try:
            import subprocess
            result = subprocess.run(
                ["kubectl", "config", "use-context", context_name],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                # Reload config to use new context
                config.load_kube_config()
                self.core_v1 = client.CoreV1Api()
                self.api_client = client.ApiClient()
                self._refresh_namespaces()
                return True
            else:
                self.logger.error(f"Failed to switch context: {result.stderr}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to switch context: {e}")
            return False

    def get_nodes(self) -> List[client.V1Node]:
        """Get all nodes in the cluster"""
        try:
            nodes = self.core_v1.list_node()
            return nodes.items
        except ApiException as e:
            self.logger.error(f"Failed to list nodes: {e}")
            return []

    def get_node_metrics(self) -> dict:
        """Get node metrics from metrics-server if available"""
        try:
            import subprocess
            # Use kubectl top nodes to get metrics
            result = subprocess.run(
                ["kubectl", "top", "nodes", "--no-headers"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                # Parse output: NAME CPU(cores) CPU% MEMORY(bytes) MEMORY%
                metrics = {}
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split()
                        if len(parts) >= 5:
                            node_name = parts[0]
                            metrics[node_name] = {
                                "cpu_cores": parts[1],
                                "cpu_percent": parts[2],
                                "memory_bytes": parts[3],
                                "memory_percent": parts[4]
                            }
                return metrics
            else:
                self.logger.warning(f"Metrics-server not available: {result.stderr}")
                return {}
        except Exception as e:
            self.logger.warning(f"Failed to get node metrics: {e}")
            return {}

    def get_pod_count_per_node(self) -> dict:
        """Get count of pods on each node"""
        try:
            pods = self.core_v1.list_pod_for_all_namespaces()
            pod_counts = {}
            for pod in pods.items:
                node_name = pod.spec.node_name
                if node_name:
                    pod_counts[node_name] = pod_counts.get(node_name, 0) + 1
            return pod_counts
        except ApiException as e:
            self.logger.error(f"Failed to count pods per node: {e}")
            return {}
