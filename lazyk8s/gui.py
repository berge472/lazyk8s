"""Textual-based GUI for lazyk8s"""

import subprocess
from typing import List, Optional
from rich.text import Text
from textual import work, on
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Footer, Static, ListView, ListItem, Label, RichLog, Input, Button,
    TabbedContent, TabPane
)
from textual.binding import Binding
from textual.reactive import reactive
from textual.timer import Timer
from kubernetes import client

from .k8s_client import K8sClient
from .config import AppConfig
from . import __version__


class StatusBar(Static):
    """Status bar displaying cluster info"""
    pass


class NamespaceItem(ListItem):
    """A list item for displaying a namespace"""

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        super().__init__(Label(f"  {namespace}"))


class NamespaceSelector(ModalScreen[Optional[str]]):
    """Modal screen for selecting a namespace"""

    CSS = """
    NamespaceSelector {
        align: center middle;
        background: black 40%;
    }

    #namespace-dialog {
        width: 60;
        height: auto;
        max-height: 80%;
        border: round $accent;
        background: $background;
        padding: 1 2;
    }

    #namespace-filter-display {
        height: 1;
        color: $accent;
        padding: 0 0 0 0;
        margin: 0 0 1 0;
    }

    #namespace-list {
        height: auto;
        max-height: 20;
        min-height: 10;
        border: none;
        background: $surface 30%;
    }

    NamespaceItem {
        padding: 0 1;
        height: 1;

        &:hover {
            background: $boost;
        }
    }

    ListView > NamespaceItem.--highlight {
        background: $accent 30%;
    }

    #namespace-help {
        dock: bottom;
        height: 1;
        background: $surface-darken-1;
        color: $text-muted;
        padding: 0 2;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+c", "cancel", "Cancel"),
    ]

    def __init__(self, namespaces: List[str], current_namespace: str):
        super().__init__()
        self.all_namespaces = sorted(namespaces)
        self.current_namespace = current_namespace
        self.filtered_namespaces = self.all_namespaces.copy()
        self.filter_text = ""

    def compose(self) -> ComposeResult:
        with Container(id="namespace-dialog"):
            yield Static("Filter: ", id="namespace-filter-display")
            yield ListView(id="namespace-list")
            yield Static("↑↓: Navigate | Enter: Select | Esc: Cancel | Type to filter", id="namespace-help")

    def on_mount(self) -> None:
        """Focus the list when mounted"""
        self.refresh_namespace_list()
        namespace_list = self.query_one("#namespace-list", ListView)
        namespace_list.focus()
        # Highlight the first item
        if len(namespace_list) > 0:
            namespace_list.index = 0

    def refresh_namespace_list(self) -> None:
        """Refresh the namespace list based on filter"""
        namespace_list = self.query_one("#namespace-list", ListView)
        namespace_list.clear()

        # Filter namespaces
        if self.filter_text:
            self.filtered_namespaces = [
                ns for ns in self.all_namespaces
                if self.filter_text.lower() in ns.lower()
            ]
        else:
            self.filtered_namespaces = self.all_namespaces.copy()

        # Add namespaces to list
        for ns in self.filtered_namespaces:
            namespace_list.append(NamespaceItem(ns))

        # Update filter display - always show it
        filter_display = self.query_one("#namespace-filter-display", Static)
        filter_display.update(f"Filter: {self.filter_text}")

        # Always highlight first item - use call_after_refresh to ensure it's applied
        def highlight_first():
            if len(namespace_list) > 0:
                namespace_list.index = 0
                namespace_list.focus()

        self.call_after_refresh(highlight_first)

    @on(ListView.Selected, "#namespace-list")
    def on_namespace_selected(self, event: ListView.Selected) -> None:
        """Handle namespace selection"""
        if isinstance(event.item, NamespaceItem):
            self.dismiss(event.item.namespace)

    def on_key(self, event) -> None:
        """Handle key presses for filtering"""
        key = event.key

        # Handle backspace
        if key == "backspace":
            if self.filter_text:
                self.filter_text = self.filter_text[:-1]
                self.refresh_namespace_list()
                event.prevent_default()
            return

        # Ignore special keys
        if key in ["escape", "enter", "up", "down", "left", "right", "tab",
                   "home", "end", "pageup", "pagedown", "ctrl+c"]:
            return

        # Handle character input (single char keys)
        if len(key) == 1 and key.isprintable():
            self.filter_text += key
            self.refresh_namespace_list()
            event.prevent_default()

    def action_cancel(self) -> None:
        """Cancel namespace selection"""
        self.dismiss(None)


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

    def __init__(self, container_name: str, is_active: bool = False) -> None:
        self.container_name = container_name
        self.is_active = is_active
        # Show indicator if active
        indicator = "[green]●[/]" if is_active else "[dim]○[/]"
        super().__init__(Label(f"{indicator} {container_name}"))

    def update_active_state(self, is_active: bool) -> None:
        """Update the active state of the container"""
        self.is_active = is_active
        indicator = "[green]●[/]" if is_active else "[dim]○[/]"
        label = self.query_one(Label)
        label.update(f"{indicator} {self.container_name}")


class LazyK8sApp(App):
    """Textual TUI for Kubernetes management"""

    # Default to tokyo-night theme
    THEME = "tokyo-night"

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
        border-title-align: left;
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
        height: 7;
        margin-top: 1;
        border: round $accent 40%;
        background: $surface 30%;
        border-title-align: left;
        border-title-color: $text-accent 50%;

        &:focus-within {
            border: round $accent 100%;
            border-title-color: $text;
            border-title-style: bold;
        }
    }

    #containers-list {
        height: 5;
        border: none;
        background: transparent;
        padding: 0 1;
    }

    #containers-list ListItem {
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
        border-title-align: left;
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
        border-title-align: left;
        border-title-color: $text-accent 50%;

        &:focus-within {
            border: round $accent 100%;
            border-title-color: $text;
            border-title-style: bold;
        }
    }

    #logs-tabs {
        height: 1fr;
        background: transparent;
    }

    #logs-tabs Tabs {
        height: 1;
        dock: top;
        background: transparent;
    }

    #logs-tabs Tab {
        display: none;
    }

    #logs-tabs Underline {
        display: none;
    }

    #logs-tabs TabPane {
        padding: 0;
    }

    #logs-panel, #events-panel, #metadata-panel {
        height: 1fr;
        border: none;
        background: transparent;
        padding: 0 1;
        overflow-x: auto;
        overflow-y: auto;
    }

    RichLog {
        scrollbar-size-horizontal: 1;
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
        Binding("x", "open_shell", "Shell"),
        Binding("f", "toggle_follow", "Follow"),
        Binding("space", "toggle_container", "Toggle Container", show=False),
        Binding("tab", "focus_next", "Next"),
        # Tab switching
        Binding("l", "switch_tab('logs-tab')", "Logs", show=False),
        Binding("e", "switch_tab('events-tab')", "Events", show=False),
        Binding("m", "switch_tab('metadata-tab')", "Metadata", show=False),
        # Horizontal scrolling for log panels
        Binding("left", "scroll_log_left", "Scroll Left", show=False),
        Binding("right", "scroll_log_right", "Scroll Right", show=False),
    ]

    selected_pod: reactive[Optional[client.V1Pod]] = reactive(None)
    selected_container: reactive[Optional[str]] = reactive(None)
    current_namespace: reactive[str] = reactive("default")
    following_logs: reactive[bool] = reactive(False)

    def __init__(self, k8s_client: K8sClient, app_config: AppConfig):
        super().__init__()
        self.k8s_client = k8s_client
        self.app_config = app_config
        self.pods: List[client.V1Pod] = []
        self.current_namespace = k8s_client.get_current_namespace()
        self._debounce_timer: Optional[Timer] = None
        self._pending_pod_index: Optional[int] = None
        self._log_follow_timer: Optional[Timer] = None
        self.active_containers: set[str] = set()  # Containers to show logs for

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
                    with TabbedContent(id="logs-tabs"):
                        with TabPane("Logs", id="logs-tab"):
                            yield RichLog(id="logs-panel", highlight=True, markup=True)
                        with TabPane("Events", id="events-tab"):
                            yield RichLog(id="events-panel", highlight=True, markup=True)
                        with TabPane("Metadata", id="metadata-tab"):
                            yield RichLog(id="metadata-panel", highlight=True, markup=True)

        # Footer with keybindings
        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted"""
        self.title = "lazyk8s"

        # Set border titles for containers
        self.query_one("#pods-container").border_title = "Pods"
        self.query_one("#containers-container").border_title = "Containers [dim](Space to toggle)[/]"
        self.query_one("#info-container").border_title = "Info"
        self.update_logs_title()

        self.refresh_status_bar()
        self.refresh_pods()

        # Auto-select first pod if available
        if self.pods:
            self.selected_pod = self.pods[0]
            self.refresh_containers()
            self.show_pod_info()
            self.show_pod_logs()
            self.show_pod_events()
            self.show_pod_metadata()

    def refresh_status_bar(self) -> None:
        """Update the status bar with cluster info"""
        host, _ = self.k8s_client.get_cluster_info()
        namespace = self.k8s_client.get_current_namespace()
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update(
            f"[b]lazyk8s[/] [dim]v{__version__}[/]  [cyan]●[/] {host}  [cyan]●[/] {namespace}"
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
            # If no containers are active, activate all by default
            if not self.active_containers and containers:
                self.active_containers = set(containers)

            for container in containers:
                is_active = container in self.active_containers
                containers_list.append(ContainerItem(container, is_active))

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
        """Show logs for the selected pod/container(s)"""
        logs_panel = self.query_one("#logs-panel", RichLog)
        logs_panel.clear()

        if not self.selected_pod:
            logs_panel.write("[dim]no pod selected[/]")
            return

        # Get active containers
        containers = self.k8s_client.get_container_names(self.selected_pod)
        if not containers:
            logs_panel.write("[dim]no containers found[/]")
            return

        active = [c for c in containers if c in self.active_containers]
        if not active:
            logs_panel.write("[dim]no active containers (press Space to toggle)[/]")
            return

        # Get interlaced logs from all active containers
        if len(active) == 1:
            # Single container - use simple method
            logs = self.k8s_client.get_pod_logs(
                self.selected_pod.metadata.name,
                active[0],
                lines=100
            )
            self._write_logs(logs_panel, logs, None)
        else:
            # Multiple containers - get combined logs with prefix
            logs = self.k8s_client.get_pod_logs_all_containers(
                self.selected_pod.metadata.name,
                active,
                lines=100
            )
            self._write_prefixed_logs(logs_panel, logs)

    def _write_logs(self, logs_panel: RichLog, logs: str, container_name: Optional[str]) -> None:
        """Write logs with colorization"""
        for line in logs.split("\n"):
            if line:
                # Apply minimal color based on log level
                if any(level in line.upper() for level in ["ERROR", "FATAL"]):
                    logs_panel.write(f"[red]{line}[/]")
                elif any(level in line.upper() for level in ["WARN", "WARNING"]):
                    logs_panel.write(f"[yellow]{line}[/]")
                else:
                    logs_panel.write(line)

    def _write_prefixed_logs(self, logs_panel: RichLog, logs: str) -> None:
        """Write logs that have kubectl prefix format: [pod/container] timestamp line"""
        for line in logs.split("\n"):
            if not line:
                continue

            # Parse kubectl prefix format: [pod/container] timestamp log_message
            # Example: [myapp-5d4b7c9f6b-abc12/app] 2024-01-15T10:30:45.123456789Z Log message
            if line.startswith("["):
                try:
                    # Extract container name from prefix
                    prefix_end = line.index("]")
                    prefix = line[1:prefix_end]  # Remove [ and ]

                    # Get container name (after the /)
                    if "/" in prefix:
                        container_name = prefix.split("/")[1]
                    else:
                        container_name = prefix

                    # Get the rest of the line (after timestamp)
                    rest = line[prefix_end + 1:].strip()

                    # Remove timestamp if present (ISO 8601 format)
                    if " " in rest:
                        parts = rest.split(" ", 1)
                        if len(parts) > 1:
                            log_message = parts[1]
                        else:
                            log_message = rest
                    else:
                        log_message = rest

                    # Format with container name and colorization
                    container_tag = f"[cyan]{container_name}[/]"

                    # Apply minimal color based on log level
                    if any(level in log_message.upper() for level in ["ERROR", "FATAL"]):
                        logs_panel.write(f"{container_tag} [red]{log_message}[/]")
                    elif any(level in log_message.upper() for level in ["WARN", "WARNING"]):
                        logs_panel.write(f"{container_tag} [yellow]{log_message}[/]")
                    else:
                        logs_panel.write(f"{container_tag} {log_message}")

                except (ValueError, IndexError):
                    # Couldn't parse, just write the line as-is
                    logs_panel.write(line)
            else:
                # No prefix, just write the line
                logs_panel.write(line)

    def show_pod_events(self) -> None:
        """Show events for the selected pod"""
        events_panel = self.query_one("#events-panel", RichLog)
        events_panel.clear()

        if not self.selected_pod:
            events_panel.write("[dim]no pod selected[/]")
            return

        events = self.k8s_client.get_pod_events(self.selected_pod.metadata.name)

        if not events or events.strip() == "":
            events_panel.write("[dim]no events found[/]")
            return

        # Display the events table from kubectl describe
        for line in events.split("\n"):
            if not line.strip():
                continue

            # Color code based on keywords in the line
            line_lower = line.lower()
            if "warning" in line_lower or "failed" in line_lower or "error" in line_lower:
                events_panel.write(f"[yellow]{line}[/]")
            elif "backoff" in line_lower or "killing" in line_lower:
                events_panel.write(f"[red]{line}[/]")
            elif "pulled" in line_lower or "created" in line_lower or "started" in line_lower:
                events_panel.write(f"[green]{line}[/]")
            else:
                events_panel.write(line)

    def show_pod_metadata(self) -> None:
        """Show metadata for the selected pod"""
        metadata_panel = self.query_one("#metadata-panel", RichLog)
        metadata_panel.clear()

        if not self.selected_pod:
            metadata_panel.write("[dim]no pod selected[/]")
            return

        pod = self.selected_pod

        # Basic metadata
        metadata_panel.write(f"[bold cyan]Basic Information[/]")
        metadata_panel.write(f"  Name: [green]{pod.metadata.name}[/]")
        metadata_panel.write(f"  Namespace: [green]{pod.metadata.namespace}[/]")
        metadata_panel.write(f"  UID: [dim]{pod.metadata.uid}[/]")
        metadata_panel.write(f"  Created: {pod.metadata.creation_timestamp}")
        metadata_panel.write("")

        # Labels
        if pod.metadata.labels:
            metadata_panel.write(f"[bold cyan]Labels[/]")
            for key, value in sorted(pod.metadata.labels.items()):
                metadata_panel.write(f"  [yellow]{key}[/]: {value}")
            metadata_panel.write("")

        # Annotations
        if pod.metadata.annotations:
            metadata_panel.write(f"[bold cyan]Annotations[/]")
            for key, value in sorted(pod.metadata.annotations.items()):
                # Truncate long values
                if len(value) > 100:
                    value = value[:97] + "..."
                metadata_panel.write(f"  [yellow]{key}[/]: [dim]{value}[/]")
            metadata_panel.write("")

        # Spec details
        metadata_panel.write(f"[bold cyan]Spec[/]")
        metadata_panel.write(f"  Node: {pod.spec.node_name or 'N/A'}")
        metadata_panel.write(f"  Service Account: {pod.spec.service_account or 'default'}")
        metadata_panel.write(f"  Restart Policy: {pod.spec.restart_policy}")
        if pod.spec.priority:
            metadata_panel.write(f"  Priority: {pod.spec.priority}")
        metadata_panel.write("")

        # Status details
        metadata_panel.write(f"[bold cyan]Status[/]")
        metadata_panel.write(f"  Phase: {pod.status.phase}")
        metadata_panel.write(f"  Pod IP: {pod.status.pod_ip or 'N/A'}")
        metadata_panel.write(f"  Host IP: {pod.status.host_ip or 'N/A'}")
        metadata_panel.write(f"  QoS Class: {pod.status.qos_class or 'N/A'}")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle cursor movement in lists with debouncing"""
        if event.list_view.id == "pods-list":
            # Cancel any existing timer
            if self._debounce_timer is not None:
                self._debounce_timer.stop()

            # Get the highlighted index
            if event.item is not None and isinstance(event.item, PodItem):
                # Store the pod index for later
                self._pending_pod_index = self.pods.index(event.item.pod)

                # Set a timer to trigger selection after 200ms
                self._debounce_timer = self.set_timer(
                    0.2,  # 200ms debounce
                    self._select_pending_pod
                )

    def _select_pending_pod(self) -> None:
        """Select the pending pod after debounce timer"""
        if self._pending_pod_index is not None and self._pending_pod_index < len(self.pods):
            self.selected_pod = self.pods[self._pending_pod_index]
            self.selected_container = None
            # Clear active containers so they get reset to all containers
            self.active_containers.clear()
            self.refresh_containers()
            self.show_pod_info()
            self.show_pod_logs()
            self.show_pod_events()
            self.show_pod_metadata()
            self._pending_pod_index = None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection (Enter key)"""
        if event.list_view.id == "pods-list":
            # Pod selected - cancel debounce and select immediately
            if self._debounce_timer is not None:
                self._debounce_timer.stop()

            if isinstance(event.item, PodItem):
                self.selected_pod = event.item.pod
                self.selected_container = None
                # Clear active containers so they get reset to all containers
                self.active_containers.clear()
                self.refresh_containers()
                self.show_pod_info()
                self.show_pod_logs()
                self.show_pod_events()
                self.show_pod_metadata()

        elif event.list_view.id == "containers-list":
            # Container selected with Enter - just mark as selected
            if isinstance(event.item, ContainerItem):
                self.selected_container = event.item.container_name

    def action_refresh(self) -> None:
        """Refresh the view"""
        self.refresh_pods()
        if self.selected_pod:
            self.refresh_containers()
            self.show_pod_info()
            self.show_pod_logs()

    def action_change_namespace(self) -> None:
        """Open namespace selector modal"""
        namespaces = self.k8s_client.get_namespaces()
        current_namespace = self.k8s_client.get_current_namespace()

        def handle_namespace_selection(selected_namespace: Optional[str]) -> None:
            """Handle namespace selection from modal"""
            if selected_namespace and selected_namespace != current_namespace:
                self.k8s_client.set_namespace(selected_namespace)
                self.current_namespace = selected_namespace
                self.refresh_status_bar()
                self.refresh_pods()

                # Auto-select first pod if available
                if self.pods:
                    self.selected_pod = self.pods[0]
                    self.refresh_containers()
                    self.show_pod_info()
                    self.show_pod_logs()
                else:
                    self.selected_pod = None
                    self.refresh_containers()
                    self.show_pod_info()
                    self.show_pod_logs()

        self.push_screen(
            NamespaceSelector(namespaces, current_namespace),
            handle_namespace_selection
        )

    def action_view_logs(self) -> None:
        """View logs for selected pod"""
        if self.selected_pod:
            self.show_pod_logs()

    def update_logs_title(self) -> None:
        """Update the logs container title to show active tab"""
        try:
            logs_tabs = self.query_one("#logs-tabs", TabbedContent)
            active_tab = logs_tabs.active

            # Build title with active tab highlighted
            if active_tab == "logs-tab":
                title = "[cyan](L)ogs[/] | [dim](E)vents[/] | [dim](M)etadata[/]"
            elif active_tab == "events-tab":
                title = "[dim](L)ogs[/] | [cyan](E)vents[/] | [dim](M)etadata[/]"
            elif active_tab == "metadata-tab":
                title = "[dim](L)ogs[/] | [dim](E)vents[/] | [cyan](M)etadata[/]"
            else:
                title = "(L)ogs | (E)vents | (M)etadata"

            # Add following indicator if active
            if self.following_logs and active_tab == "logs-tab":
                title = title.replace("(L)ogs", "(L)ogs [green]●[/]")

            self.query_one("#logs-container").border_title = title
        except Exception:
            pass

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a specific tab"""
        try:
            logs_tabs = self.query_one("#logs-tabs", TabbedContent)
            logs_tabs.active = tab_id
            self.update_logs_title()
        except Exception:
            pass

    def action_scroll_log_left(self) -> None:
        """Scroll the active log panel left"""
        try:
            logs_tabs = self.query_one("#logs-tabs", TabbedContent)
            active_tab = logs_tabs.active

            # Get the active panel
            if active_tab == "logs-tab":
                panel = self.query_one("#logs-panel", RichLog)
            elif active_tab == "events-tab":
                panel = self.query_one("#events-panel", RichLog)
            elif active_tab == "metadata-tab":
                panel = self.query_one("#metadata-panel", RichLog)
            else:
                return

            # Scroll left
            panel.scroll_left(animate=False)
        except Exception:
            pass

    def action_scroll_log_right(self) -> None:
        """Scroll the active log panel right"""
        try:
            logs_tabs = self.query_one("#logs-tabs", TabbedContent)
            active_tab = logs_tabs.active

            # Get the active panel
            if active_tab == "logs-tab":
                panel = self.query_one("#logs-panel", RichLog)
            elif active_tab == "events-tab":
                panel = self.query_one("#events-panel", RichLog)
            elif active_tab == "metadata-tab":
                panel = self.query_one("#metadata-panel", RichLog)
            else:
                return

            # Scroll right
            panel.scroll_right(animate=False)
        except Exception:
            pass

    def action_toggle_container(self) -> None:
        """Toggle container log visibility (Space key)"""
        # Only work when containers list is focused
        containers_list = self.query_one("#containers-list", ListView)
        if self.focused == containers_list:
            # Get the highlighted item
            if containers_list.highlighted_child and isinstance(containers_list.highlighted_child, ContainerItem):
                item = containers_list.highlighted_child
                container_name = item.container_name

                # Toggle container in active set
                if container_name in self.active_containers:
                    self.active_containers.discard(container_name)
                else:
                    self.active_containers.add(container_name)

                # Update the item's visual state
                item.update_active_state(container_name in self.active_containers)

                # Refresh logs to show/hide this container's logs
                self.show_pod_logs()

    def action_toggle_follow(self) -> None:
        """Toggle log following"""
        self.following_logs = not self.following_logs

        # Update title to show following indicator
        self.update_logs_title()

        # Start/stop following timer
        if self.following_logs:
            if self._log_follow_timer is None:
                self._log_follow_timer = self.set_interval(2.0, self._refresh_logs)
        else:
            if self._log_follow_timer is not None:
                self._log_follow_timer.stop()
                self._log_follow_timer = None

    def _refresh_logs(self) -> None:
        """Refresh logs when following"""
        if self.following_logs and self.selected_pod:
            self.show_pod_logs()

    def action_open_shell(self) -> None:
        """Open shell in selected pod/container"""
        if not self.selected_pod:
            return

        containers = self.k8s_client.get_container_names(self.selected_pod)
        if not containers:
            return

        # Use highlighted container if containers list is focused, otherwise use first container
        containers_list = self.query_one("#containers-list", ListView)
        if self.focused == containers_list and containers_list.highlighted_child:
            if isinstance(containers_list.highlighted_child, ContainerItem):
                container = containers_list.highlighted_child.container_name
            else:
                container = containers[0]
        else:
            container = containers[0]

        namespace = self.k8s_client.get_current_namespace()
        pod_name = self.selected_pod.metadata.name

        # Exit the TUI temporarily
        with self.suspend():
            # Colorful banner
            print(f"\033[36m→\033[0m \033[2mShell:\033[0m \033[33m{namespace}\033[0m:\033[32m{pod_name}\033[0m.\033[35m{container}\033[0m")

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

            # Colorful exit message
            print(f"\n\033[36m←\033[0m \033[2mPress\033[0m \033[1;32mEnter\033[0m \033[2mto return to\033[0m \033[1;36mlazyk8s\033[0m\033[2m...\033[0m")
            input()

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
