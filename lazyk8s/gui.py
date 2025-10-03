"""Textual-based GUI for lazyk8s"""

import subprocess
from typing import List, Optional
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Static, ListView, ListItem, Label, RichLog
from textual.binding import Binding
from textual.reactive import reactive
from kubernetes import client

from .k8s_client import K8sClient
from .config import AppConfig


class StatusBar(Static):
    """Status bar displaying cluster info"""
    pass


class PodItem(ListItem):
    """A list item for displaying a pod"""

    def __init__(self, pod: client.V1Pod, k8s_client: K8sClient) -> None:
        self.pod = pod
        self.k8s_client = k8s_client
        status = k8s_client.get_pod_status(pod)

        # Determine status with simple colored bullet
        phase = pod.status.phase
        if phase == "Running":
            ready = sum(1 for cs in (pod.status.container_statuses or []) if cs.ready)
            total = len(pod.status.container_statuses or [])
            if ready == total and total > 0:
                icon = "[green]●[/]"
            else:
                icon = "[yellow]●[/]"
        elif phase == "Pending":
            icon = "[yellow]●[/]"
        else:
            icon = "[red]●[/]"

        # Simple format: status • name
        label_text = f"{icon} {pod.metadata.name}"
        super().__init__(Label(label_text))


class ContainerItem(ListItem):
    """A list item for displaying a container"""

    def __init__(self, container_name: str) -> None:
        self.container_name = container_name
        super().__init__(Label(f"  {container_name}"))


class LazyK8sApp(App):
    """Textual TUI for Kubernetes management"""

    CSS = """
    * {
        scrollbar-color: $primary 30%;
        scrollbar-color-hover: $primary 60%;
        scrollbar-color-active: $primary;
        scrollbar-background: $surface;
        scrollbar-background-hover: $surface;
        scrollbar-background-active: $surface;
        scrollbar-size-vertical: 1;
    }

    Screen {
        background: $background;
    }

    StatusBar {
        dock: top;
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 2;
    }

    #main-container {
        layout: horizontal;
        height: 1fr;
        padding: 0 1;
    }

    #left-panel {
        width: 35%;
        height: 1fr;
    }

    #pods-container {
        height: 1fr;
        border: round $accent 40%;
        background: $surface 30%;
        border-title-align: right;
        border-title-color: $text-accent 50%;

        &:focus-within {
            border: round $accent 100%;
            border-title-color: $text;
            border-title-style: bold;
        }
    }

    #pods-list {
        height: 1fr;
        border: none;
        background: transparent;
        padding: 0 1;
    }

    #containers-container {
        height: auto;
        margin-top: 1;
        border: round $accent 40%;
        background: $surface 30%;
        border-title-align: right;
        border-title-color: $text-accent 50%;

        &:focus-within {
            border: round $accent 100%;
            border-title-color: $text;
            border-title-style: bold;
        }
    }

    #containers-list {
        height: auto;
        max-height: 8;
        border: none;
        background: transparent;
        padding: 0 1;
    }

    #right-panel {
        width: 65%;
        height: 1fr;
        margin-left: 1;
    }

    #info-container {
        height: auto;
        border: round $accent 40%;
        background: $surface 20%;
        border-title-align: right;
        border-title-color: $text-accent 50%;
    }

    #info-panel {
        height: auto;
        max-height: 10;
        border: none;
        background: transparent;
        padding: 1 2;
        color: $text;
    }

    #logs-container {
        height: 1fr;
        margin-top: 1;
        border: round $accent 40%;
        background: $surface 20%;
        border-title-align: right;
        border-title-color: $text-accent 50%;

        &:focus-within {
            border: round $accent 100%;
            border-title-color: $text;
            border-title-style: bold;
        }
    }

    #logs-panel {
        height: 1fr;
        border: none;
        background: transparent;
        padding: 0 1;
    }

    ListView {
        height: 100%;
        padding: 0;
    }

    ListItem {
        padding: 0 1;
        height: 1;

        &:hover {
            background: $boost;
        }
    }

    .panel-title {
        color: $text-accent 60%;
        text-align: right;
        padding: 0 1;
    }

    Footer {
        background: $surface;
        padding-left: 2;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("n", "change_namespace", "Namespace"),
        Binding("l", "view_logs", "Logs"),
        Binding("x", "open_shell", "Shell"),
        Binding("tab", "focus_next", "Next Panel"),
    ]

    selected_pod: reactive[Optional[client.V1Pod]] = reactive(None)
    selected_container: reactive[Optional[str]] = reactive(None)
    current_namespace: reactive[str] = reactive("default")

    def __init__(self, k8s_client: K8sClient, app_config: AppConfig):
        super().__init__()
        self.k8s_client = k8s_client
        self.app_config = app_config
        self.pods: List[client.V1Pod] = []
        self.current_namespace = k8s_client.get_current_namespace()

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        # Status bar at top
        yield StatusBar(id="status-bar")

        # Main content area
        with Horizontal(id="main-container"):
            # Left panel with pods and containers
            with Vertical(id="left-panel"):
                with Container(id="pods-container"):
                    yield ListView(id="pods-list")
                with Container(id="containers-container"):
                    yield ListView(id="containers-list")

            # Right panel with info and logs
            with Vertical(id="right-panel"):
                with Container(id="info-container"):
                    yield Static(id="info-panel")
                with Container(id="logs-container"):
                    yield RichLog(id="logs-panel", highlight=True, markup=True)

        # Footer with keybindings
        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted"""
        self.title = "lazyk8s"

        # Set border titles for containers
        self.query_one("#pods-container").border_title = "Pods"
        self.query_one("#containers-container").border_title = "Containers"
        self.query_one("#info-container").border_title = "Info"
        self.query_one("#logs-container").border_title = "Logs"

        self.refresh_status_bar()
        self.refresh_pods()

    def refresh_status_bar(self) -> None:
        """Update the status bar with cluster info"""
        host, version = self.k8s_client.get_cluster_info()
        namespace = self.k8s_client.get_current_namespace()
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update(
            f"[b]lazyk8s[/] [dim]{version}[/]  [cyan]●[/] {namespace}"
        )

    def refresh_pods(self) -> None:
        """Refresh the pods list"""
        self.pods = self.k8s_client.get_pods()
        pods_list = self.query_one("#pods-list", ListView)
        pods_list.clear()

        for pod in self.pods:
            pods_list.append(PodItem(pod, self.k8s_client))

    def refresh_containers(self) -> None:
        """Refresh the containers list for selected pod"""
        containers_list = self.query_one("#containers-list", ListView)
        containers_list.clear()

        if self.selected_pod:
            containers = self.k8s_client.get_container_names(self.selected_pod)
            for container in containers:
                containers_list.append(ContainerItem(container))

    def show_pod_info(self) -> None:
        """Show information about the selected pod"""
        info_panel = self.query_one("#info-panel", Static)

        if not self.selected_pod:
            info_panel.update("[dim]no pod selected[/]")
            return

        pod = self.selected_pod
        info_lines = [
            f"[b]{pod.metadata.name}[/]",
            f"[dim]node:[/] {pod.spec.node_name or 'n/a'}  [dim]ip:[/] {pod.status.pod_ip or 'n/a'}",
            "",
        ]

        for container in pod.spec.containers:
            info_lines.append(f"[cyan]●[/] {container.name}")
            info_lines.append(f"  [dim]{container.image}[/]")

        info_panel.update("\n".join(info_lines))

    def show_pod_logs(self) -> None:
        """Show logs for the selected pod/container"""
        logs_panel = self.query_one("#logs-panel", RichLog)
        logs_panel.clear()

        if not self.selected_pod:
            logs_panel.write("[dim]no pod selected[/]")
            return

        # Get first container if no container selected
        containers = self.k8s_client.get_container_names(self.selected_pod)
        if not containers:
            logs_panel.write("[dim]no containers found[/]")
            return

        container = self.selected_container or containers[0]
        logs = self.k8s_client.get_pod_logs(
            self.selected_pod.metadata.name,
            container,
            lines=100
        )

        # Write logs with subtle colorization
        for line in logs.split("\n"):
            if line:
                # Apply minimal color based on log level
                if any(level in line.upper() for level in ["ERROR", "FATAL"]):
                    logs_panel.write(f"[red]{line}[/]")
                elif any(level in line.upper() for level in ["WARN", "WARNING"]):
                    logs_panel.write(f"[yellow]{line}[/]")
                else:
                    logs_panel.write(line)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection"""
        if event.list_view.id == "pods-list":
            # Pod selected
            if isinstance(event.item, PodItem):
                self.selected_pod = event.item.pod
                self.selected_container = None
                self.refresh_containers()
                self.show_pod_info()
                self.show_pod_logs()

        elif event.list_view.id == "containers-list":
            # Container selected
            if isinstance(event.item, ContainerItem):
                self.selected_container = event.item.container_name
                self.show_pod_logs()

    def action_refresh(self) -> None:
        """Refresh the view"""
        self.refresh_pods()
        if self.selected_pod:
            self.refresh_containers()
            self.show_pod_info()
            self.show_pod_logs()

    def action_change_namespace(self) -> None:
        """Open namespace selector (simplified - just refresh current)"""
        # In a full implementation, this would show a modal with namespace list
        # For now, just refresh
        self.refresh_status_bar()

    def action_view_logs(self) -> None:
        """View logs for selected pod"""
        if self.selected_pod:
            self.show_pod_logs()

    def action_open_shell(self) -> None:
        """Open shell in selected pod"""
        if not self.selected_pod:
            return

        containers = self.k8s_client.get_container_names(self.selected_pod)
        if not containers:
            return

        container = self.selected_container or containers[0]
        namespace = self.k8s_client.get_current_namespace()
        pod_name = self.selected_pod.metadata.name

        # Exit the TUI temporarily
        with self.suspend():
            print(f"\n● Opening shell: {namespace}/{pod_name}/{container}\n")

            for shell in ["/bin/bash", "/bin/sh", "/bin/ash"]:
                try:
                    result = subprocess.run([
                        "kubectl", "exec", "-it",
                        "-n", namespace,
                        pod_name,
                        "-c", container,
                        "--", shell
                    ])
                    if result.returncode == 0:
                        break
                except Exception:
                    continue

            input("\nPress Enter to return to lazyk8s...")

        # Refresh the display after returning
        self.refresh_pods()
        if self.selected_pod:
            self.show_pod_info()
            self.show_pod_logs()


class Gui:
    """GUI wrapper class"""

    def __init__(self, k8s_client: K8sClient, app_config: AppConfig):
        self.k8s_client = k8s_client
        self.app_config = app_config
        self.app = LazyK8sApp(k8s_client, app_config)

    def run(self) -> None:
        """Run the GUI application"""
        self.app.run()
