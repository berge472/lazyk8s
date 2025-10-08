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

from lazyk8s.helpers.formatHelper import alignText


class StatusBar(Static):
    """Status bar displaying cluster info"""
    pass


class NamespaceItem(ListItem):
    """A list item for displaying a namespace"""

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        super().__init__(Label(f"  {namespace}"))


class ConfirmDialog(ModalScreen[bool]):
    """Modal screen for confirmation dialogs"""

    CSS = """
    ConfirmDialog {
        align: center middle;
        background: black 40%;
    }

    #confirm-dialog {
        width: 60;
        height: auto;
        border: round $error;
        background: $background;
        padding: 1 2;
    }

    #confirm-title {
        width: 100%;
        height: 1;
        content-align: center middle;
        color: $error;
        text-style: bold;
        padding: 0 0 1 0;
    }

    #confirm-message {
        width: 100%;
        height: auto;
        content-align: center middle;
        padding: 1 0;
    }

    #confirm-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        padding: 1 0;
    }

    #confirm-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("n", "cancel", "No"),
        Binding("y", "confirm", "Yes"),
        # Vim navigation
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self, message: str, title: str = "Confirm"):
        super().__init__()
        self.message = message
        self.title = title

    def compose(self) -> ComposeResult:
        with Container(id="confirm-dialog"):
            yield Static(self.title, id="confirm-title")
            yield Static(self.message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes (y)", variant="error", id="confirm-yes")
                yield Button("No (n)", variant="primary", id="confirm-no")

    def on_mount(self) -> None:
        """Focus the No button by default"""
        self.query_one("#confirm-no", Button).focus()

    @on(Button.Pressed, "#confirm-yes")
    def on_confirm_yes(self) -> None:
        """User confirmed"""
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-no")
    def on_confirm_no(self) -> None:
        """User cancelled"""
        self.dismiss(False)

    def action_confirm(self) -> None:
        """Confirm action"""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel action"""
        self.dismiss(False)


class UsernameInputDialog(ModalScreen[Optional[str]]):
    """Modal screen for inputting SSH username"""

    CSS = """
    UsernameInputDialog {
        align: center middle;
        background: black 40%;
    }

    #username-dialog {
        width: 60;
        height: auto;
        border: round $primary;
        background: $background;
        padding: 1 2;
    }

    #username-title {
        width: 100%;
        height: 1;
        content-align: center middle;
        color: $primary;
        text-style: bold;
        padding: 0 0 1 0;
    }

    #username-label {
        width: 100%;
        height: auto;
        padding: 1 0 0 0;
    }

    #username-input {
        width: 100%;
        margin: 1 0;
    }

    #username-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        padding: 1 0;
    }

    #username-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        # Vim navigation
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self, node_name: str):
        super().__init__()
        self.node_name = node_name

    def compose(self) -> ComposeResult:
        with Container(id="username-dialog"):
            yield Static("SSH Connection", id="username-title")
            yield Static(f"Enter username for node: {self.node_name}", id="username-label")
            yield Input(placeholder="Username (e.g., ubuntu, admin)", id="username-input")
            with Horizontal(id="username-buttons"):
                yield Button("Connect", variant="primary", id="username-connect")
                yield Button("Cancel", variant="default", id="username-cancel")

    def on_mount(self) -> None:
        """Focus the input field on mount"""
        self.query_one("#username-input", Input).focus()

    @on(Input.Submitted, "#username-input")
    def on_input_submitted(self) -> None:
        """Handle Enter key press in the input field"""
        username = self.query_one("#username-input", Input).value.strip()
        if username:
            self.dismiss(username)

    @on(Button.Pressed, "#username-connect")
    def on_connect(self) -> None:
        """User wants to connect"""
        username = self.query_one("#username-input", Input).value.strip()
        if username:
            self.dismiss(username)
        else:
            self.query_one("#username-input", Input).focus()

    @on(Button.Pressed, "#username-cancel")
    def on_cancel(self) -> None:
        """User cancelled"""
        self.dismiss(None)

    def action_cancel(self) -> None:
        """Cancel action"""
        self.dismiss(None)


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
        # Vim navigation
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
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
            yield Static("↑↓/jk: Navigate | Enter: Select | Esc: Cancel | Type to filter", id="namespace-help")

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

        # Ignore special keys (including vim navigation)
        if key in ["escape", "enter", "up", "down", "left", "right", "tab",
                   "home", "end", "pageup", "pagedown", "ctrl+c", "j", "k", "h", "l"]:
            return

        # Handle character input (single char keys)
        if len(key) == 1 and key.isprintable():
            self.filter_text += key
            self.refresh_namespace_list()
            event.prevent_default()

    def action_cancel(self) -> None:
        """Cancel namespace selection"""
        self.dismiss(None)


class ContextItem(ListItem):
    """A list item for displaying a kubeconfig context"""

    def __init__(self, context: dict, is_current: bool = False) -> None:
        self.context = context
        self.context_name = context['name']
        self.is_current = is_current

        # Show indicator if current context
        indicator = "[green]●[/]" if is_current else " "
        super().__init__(Label(f"{indicator} {self.context_name}"))


class ClusterSelector(ModalScreen[Optional[str]]):
    """Modal screen for selecting a cluster context"""

    CSS = """
    ClusterSelector {
        align: center middle;
        background: black 40%;
    }

    #cluster-dialog {
        width: 70;
        height: auto;
        max-height: 80%;
        border: round $accent;
        background: $background;
        padding: 1 2;
    }

    #cluster-title {
        height: 1;
        color: $accent;
        text-style: bold;
        padding: 0 0 1 0;
    }

    #cluster-list {
        height: auto;
        max-height: 20;
        min-height: 10;
        border: none;
        background: $surface 30%;
    }

    ContextItem {
        padding: 0 1;
        height: 1;

        &:hover {
            background: $boost;
        }
    }

    ListView > ContextItem.--highlight {
        background: $accent 30%;
    }

    #cluster-help {
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
        # Vim navigation
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self, contexts: List[dict], current_context: dict):
        super().__init__()
        self.contexts = contexts
        self.current_context = current_context

    def compose(self) -> ComposeResult:
        with Container(id="cluster-dialog"):
            yield Static("Select Cluster Context", id="cluster-title")
            yield ListView(id="cluster-list")
            yield Static("↑↓/jk: Navigate | Enter: Select | Esc: Cancel", id="cluster-help")

    def on_mount(self) -> None:
        """Populate the context list when mounted"""
        cluster_list = self.query_one("#cluster-list", ListView)

        current_name = self.current_context.get('name', '') if self.current_context else ''

        for ctx in self.contexts:
            is_current = ctx['name'] == current_name
            cluster_list.append(ContextItem(ctx, is_current))

        cluster_list.focus()
        if len(cluster_list) > 0:
            cluster_list.index = 0

    @on(ListView.Selected, "#cluster-list")
    def on_context_selected(self, event: ListView.Selected) -> None:
        """Handle context selection"""
        if isinstance(event.item, ContextItem):
            self.dismiss(event.item.context_name)

    def action_cancel(self) -> None:
        """Cancel context selection"""
        self.dismiss(None)


class NodeItem(ListItem):
    """A list item for displaying a node"""

    def __init__(self, node: client.V1Node, metrics: dict, pod_count: int, max_pods: int) -> None:
        self.node = node
        self.node_name = node.metadata.name

        # Get node status
        status = "Ready" if any(
            cond.type == "Ready" and cond.status == "True"
            for cond in node.status.conditions
        ) else "NotReady"
        status_icon = "[green]●[/]" if status == "Ready" else "[red]●[/]"

        # Pod count color
        pod_color = "green" if pod_count < max_pods * 0.8 else "yellow" if pod_count < max_pods else "red"

        # Get roles - check multiple label formats
        roles = []
        if node.metadata.labels:
            for label, value in node.metadata.labels.items():
                # Check both formats: node-role.kubernetes.io/<role> and node-role.kubernetes.io/<role>=""
                if 'node-role.kubernetes.io/' in label:
                    role = label.split('/')[-1]
                    if role:
                        roles.append(role)
                # Also check for control-plane/master specific labels
                elif label == 'node-role.kubernetes.io/control-plane' or label == 'node-role.kubernetes.io/master':
                    if 'control-plane' not in roles and 'master' not in roles:
                        roles.append('control-plane')
        role_str = ",".join(roles) if roles else "worker"

        # CPU and Memory utilization
        cpu_str = ""
        mem_str = ""
        if node.metadata.name in metrics:
            node_metrics = metrics[node.metadata.name]
            cpu_percent = node_metrics['cpu_percent'].rstrip('%')
            mem_percent = node_metrics['memory_percent'].rstrip('%')

            # Color code based on utilization
            try:
                cpu_val = float(cpu_percent)
                cpu_color = "green" if cpu_val < 70 else "yellow" if cpu_val < 90 else "red"
                cpu_str = f"[{cpu_color}]" + alignText(f"CPU:{cpu_percent}%", 12) + "[/]"
            except ValueError:
                cpu_str = alignText(f"CPU:{cpu_percent}%", 12)

            try:
                mem_val = float(mem_percent)
                mem_color = "green" if mem_val < 70 else "yellow" if mem_val < 90 else "red"
                mem_str = f"[{mem_color}]"+ alignText(f"Mem:{mem_percent}%", 12) + "[/]"
            except ValueError:
                mem_str = alignText(f"Mem:{mem_percent}%", 12)
        else:
            cpu_str = f"[dim]" + alignText("CPU:N/A", 12) + "[/]"
            mem_str = f"[dim]" + alignText("Mem:N/A", 12) + "[/]"

        podStr = alignText(f"{pod_count}/{max_pods}", 12, alignment='right')
        nameStr = alignText(self.node_name, 30, alignment='left', trimFromFront=True)

        # Format: status • name | pods | cpu | mem | role
        label_text = f"{status_icon} {nameStr} {podStr}   {cpu_str} {mem_str} [dim]{role_str}[/]"
        super().__init__(Label(label_text))


class ClusterOverview(ModalScreen[bool]):
    """Modal screen for displaying cluster overview with node information"""

    CSS = """
    ClusterOverview {
        align: center middle;
        background: black 40%;
    }

    #overview-dialog {
        width: 90%;
        height: 90%;
        border: round $accent;
        background: $background;
        padding: 1 2;
    }

    #overview-title {
        height: 1;
        color: $accent;
        text-style: bold;
        padding: 0 0 1 0;
    }

    #overview-summary {
        height: auto;
        border: none;
        background: transparent;
        padding: 0 1;
    }

    #nodes-container {
        height: 20;
        margin-top: 1;
        border: round $accent 40%;
        background: $surface 30%;
        border-title-align: left;
        border-title-color: $text-accent 50%;
    }

    #nodes-list {
        height: 1fr;
        border: none;
        background: transparent;
        padding: 0 1;
    }

    NodeItem {
        padding: 0 1;
        height: 1;

        &:hover {
            background: $boost;
        }
    }

    ListView > NodeItem.--highlight {
        background: $accent 30%;
    }

    #node-details {
        height: 1fr;
        margin-top: 1;
        border: round $accent 40%;
        background: $surface 20%;
        border-title-align: left;
        border-title-color: $text-accent 50%;
    }

    #node-details-content {
        height: 1fr;
        border: none;
        background: transparent;
        padding: 1 2;
        overflow-y: auto;
    }

    #overview-help {
        dock: bottom;
        height: 1;
        background: $surface-darken-1;
        color: $text-muted;
        padding: 0 2;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("ctrl+c", "close", "Close"),
        Binding("r", "refresh", "Refresh"),
        Binding("x", "ssh_node", "SSH"),
        # Vim navigation
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self, k8s_client: K8sClient):
        super().__init__()
        self.k8s_client = k8s_client
        self.nodes = []
        self.selected_node = None

    def compose(self) -> ComposeResult:
        with Container(id="overview-dialog"):
            yield Static("Cluster Overview", id="overview-title")
            yield Static(id="overview-summary")
            with Container(id="nodes-container"):
                yield ListView(id="nodes-list")
            with Container(id="node-details"):
                yield RichLog(id="node-details-content", highlight=True, markup=True)
            yield Static("↑↓/jk: Navigate | x: SSH | r: Refresh | Esc: Close", id="overview-help")

    def on_mount(self) -> None:
        """Load and display cluster overview"""
        self.query_one("#nodes-container").border_title = "Nodes"
        self.query_one("#node-details").border_title = "Node Details"
        self.refresh_overview()

    def refresh_overview(self) -> None:
        """Refresh the cluster overview data"""
        # Get cluster info
        cluster_name, _ = self.k8s_client.get_cluster_info()

        # Get nodes
        self.nodes = self.k8s_client.get_nodes()
        if not self.nodes:
            summary = self.query_one("#overview-summary", Static)
            summary.update("[yellow]No nodes found[/]")
            return

        # Get metrics and pod counts
        metrics = self.k8s_client.get_node_metrics()
        pod_counts = self.k8s_client.get_pod_count_per_node()

        # Update summary
        total_pods = sum(pod_counts.values())
        summary = self.query_one("#overview-summary", Static)
        summary.update(f"[bold cyan]Cluster:[/] {cluster_name}  [bold cyan]Nodes:[/] {len(self.nodes)}  [bold cyan]Total Pods:[/] {total_pods}")

        # Populate nodes list
        nodes_list = self.query_one("#nodes-list", ListView)
        nodes_list.clear()

        for node in self.nodes:
            name = node.metadata.name
            pod_count = pod_counts.get(name, 0)

            # Get max pods
            max_pods = 110
            if node.status.allocatable and 'pods' in node.status.allocatable:
                max_pods = int(node.status.allocatable['pods'])

            nodes_list.append(NodeItem(node, metrics, pod_count, max_pods))

        # Focus and select first node
        nodes_list.focus()
        if len(nodes_list) > 0:
            nodes_list.index = 0

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle node selection"""
        if event.list_view.id == "nodes-list" and isinstance(event.item, NodeItem):
            self.selected_node = event.item.node
            self.show_node_details()

    def show_node_details(self) -> None:
        """Show detailed information about the selected node"""
        details_content = self.query_one("#node-details-content", RichLog)
        details_content.clear()

        if not self.selected_node:
            details_content.write("[dim]No node selected[/]")
            return

        node = self.selected_node

        # Basic info
        details_content.write(f"[bold cyan]Name:[/] {node.metadata.name}")

        # IP addresses
        if node.status.addresses:
            details_content.write(f"[bold cyan]Addresses:[/]")
            for addr in node.status.addresses:
                details_content.write(f"  {addr.type}: [green]{addr.address}[/]")
        details_content.write("")

        # Status
        details_content.write(f"[bold cyan]Status:[/]")
        for cond in node.status.conditions:
            status_color = "green" if cond.status == "True" else "red"
            details_content.write(f"  {cond.type}: [{status_color}]{cond.status}[/]")
        details_content.write("")

        # Version info
        if node.status.node_info:
            info = node.status.node_info
            details_content.write(f"[bold cyan]System Info:[/]")
            details_content.write(f"  Kubelet: {info.kubelet_version}")
            details_content.write(f"  OS: {info.operating_system}")
            details_content.write(f"  OS Image: {info.os_image}")
            details_content.write(f"  Kernel: {info.kernel_version}")
            details_content.write(f"  Container Runtime: {info.container_runtime_version}")
            details_content.write("")

        # Capacity and Allocatable
        if node.status.capacity:
            details_content.write(f"[bold cyan]Capacity:[/]")
            details_content.write(f"  CPU: {node.status.capacity.get('cpu', 'N/A')}")
            details_content.write(f"  Memory: {node.status.capacity.get('memory', 'N/A')}")
            details_content.write(f"  Pods: {node.status.capacity.get('pods', 'N/A')}")
            details_content.write("")

        if node.status.allocatable:
            details_content.write(f"[bold cyan]Allocatable:[/]")
            details_content.write(f"  CPU: {node.status.allocatable.get('cpu', 'N/A')}")
            details_content.write(f"  Memory: {node.status.allocatable.get('memory', 'N/A')}")
            details_content.write(f"  Pods: {node.status.allocatable.get('pods', 'N/A')}")
            details_content.write("")

        # Labels
        if node.metadata.labels:
            details_content.write(f"[bold cyan]Labels:[/]")
            for key, value in sorted(node.metadata.labels.items()):
                details_content.write(f"  [yellow]{key}[/]: {value}")

    def action_refresh(self) -> None:
        """Refresh the overview"""
        self.refresh_overview()

    async def action_ssh_node(self) -> None:
        """SSH into the selected node"""
        if not self.selected_node:
            return

        node = self.selected_node

        # Get IP address (prefer ExternalIP, fallback to InternalIP)
        ip_address = None
        if node.status.addresses:
            # Try to find ExternalIP first
            for addr in node.status.addresses:
                if addr.type == "ExternalIP":
                    ip_address = addr.address
                    break

            # Fallback to InternalIP
            if not ip_address:
                for addr in node.status.addresses:
                    if addr.type == "InternalIP":
                        ip_address = addr.address
                        break

        if not ip_address:
            return

        # Show username input dialog
        username = await self.app.push_screen(
            UsernameInputDialog(node.metadata.name)
        )

        if not username:
            return  # User cancelled

        # Exit the TUI temporarily
        with self.app.suspend():
            # Colorful banner
            separator = "─" * 60
            print(f"\033[36m{separator}\033[0m")
            print(f"\033[36m→ \033[1;37mSSH to Node\033[0m")
            print(f"  \033[2mNode:\033[0m \033[32m{node.metadata.name}\033[0m")
            print(f"  \033[2mUser:\033[0m \033[33m{username}\033[0m")
            print(f"  \033[2mIP:\033[0m \033[35m{ip_address}\033[0m")
            print(f"\033[36m{separator}\033[0m\n")

            # Attempt SSH
            import subprocess
            try:
                subprocess.run(["ssh", f"{username}@{ip_address}"])
            except Exception as e:
                print(f"\n\033[31mSSH failed: {e}\033[0m")

            # Exit message
            print(f"\n\033[36m{separator}\033[0m")
            print(f"\033[36m← \033[1;37mExited SSH\033[0m")
            print(f"\033[2mPress \033[0m\033[1;32mEnter\033[0m\033[2m to return to \033[0m\033[1;36mlazyk8s\033[0m\033[2m...\033[0m")
            print(f"\033[36m{separator}\033[0m")
            input()

    def action_close(self) -> None:
        """Close the overview"""
        self.dismiss(True)


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
        Binding("c", "cluster_overview", "Cluster"),
        Binding("x", "open_shell", "Shell"),
        Binding("f", "toggle_follow", "Follow"),
        Binding("d", "delete_pod", "Delete"),
        Binding("space", "toggle_container", "Toggle Container", show=False),
        Binding("tab", "focus_next", "Next"),
        # Tab switching (capital letters)
        Binding("L", "switch_tab('logs-tab')", "Logs", show=False),
        Binding("E", "switch_tab('events-tab')", "Events", show=False),
        Binding("M", "switch_tab('metadata-tab')", "Metadata", show=False),
        # Vim navigation
        Binding("h", "scroll_log_left", "Scroll Left", show=False),
        Binding("l", "scroll_log_right", "Scroll Right", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        # Arrow keys (keep existing)
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

    def action_cluster_overview(self) -> None:
        """Open cluster overview or context selector if multiple contexts"""
        # Get all contexts
        contexts, current_context = self.k8s_client.get_contexts()

        # If multiple contexts, show selector first
        if len(contexts) > 1:
            def handle_context_selection(selected_context: Optional[str]) -> None:
                """Handle context selection from modal"""
                if selected_context and selected_context != current_context.get('name', ''):
                    # Switch context
                    success = self.k8s_client.switch_context(selected_context)
                    if success:
                        # Refresh everything
                        self.refresh_status_bar()
                        self.refresh_pods()
                        self.selected_pod = None
                        self.selected_container = None
                        self.active_containers.clear()
                        self.refresh_containers()
                        self.show_pod_info()
                        self.show_pod_logs()

                # Show cluster overview
                self.push_screen(ClusterOverview(self.k8s_client))

            self.push_screen(
                ClusterSelector(contexts, current_context),
                handle_context_selection
            )
        else:
            # Single context, just show overview
            self.push_screen(ClusterOverview(self.k8s_client))

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

    def action_cursor_down(self) -> None:
        """Move cursor down in focused list"""
        try:
            focused = self.focused
            if isinstance(focused, ListView):
                focused.action_cursor_down()
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        """Move cursor up in focused list"""
        try:
            focused = self.focused
            if isinstance(focused, ListView):
                focused.action_cursor_up()
        except Exception:
            pass

    def on_key(self, event) -> None:
        """Handle key presses for custom navigation"""
        key = event.key
        pods_list = self.query_one("#pods-list", ListView)
        containers_list = self.query_one("#containers-list", ListView)

        # When pods panel is focused
        if self.focused == pods_list:
            # Left/right arrows or h/l cycle through containers
            if key in ["left", "right", "h", "l"]:
                if len(containers_list) > 0:
                    if key in ["right", "l"]:
                        containers_list.action_cursor_down()
                    else:  # left or h
                        containers_list.action_cursor_up()
                    event.prevent_default()
                    event.stop()
                    return

            # Space toggles container logs
            elif key == "space":
                self.action_toggle_container()
                event.prevent_default()
                event.stop()
                return

        # When logs container has focus (check if focused widget is inside logs container)
        try:
            logs_tabs = self.query_one("#logs-tabs", TabbedContent)
            logs_container = self.query_one("#logs-container")

            # Check if the focused widget is the TabbedContent or any of its children
            if self.focused == logs_tabs or (self.focused and self.focused in logs_tabs.query("*")):
                if key in ["left", "right", "h", "l"]:
                    if key in ["left", "h"]:
                        self.action_scroll_log_left()
                    else:
                        self.action_scroll_log_right()
                    event.prevent_default()
                    event.stop()
                    return
        except Exception:
            pass

    def action_toggle_container(self) -> None:
        """Toggle container log visibility (Space key)"""
        containers_list = self.query_one("#containers-list", ListView)

        # Get the highlighted item from containers list
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
            # Colorful banner with separator line
            separator = "─" * 60
            print(f"\033[36m{separator}\033[0m")
            print(f"\033[36m→ \033[1;37mEntering Shell\033[0m")
            print(f"  \033[2mNamespace:\033[0m \033[33m{namespace}\033[0m")
            print(f"  \033[2mPod:\033[0m \033[32m{pod_name}\033[0m")
            print(f"  \033[2mContainer:\033[0m \033[35m{container}\033[0m")
            print(f"\033[36m{separator}\033[0m\n")

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

            # Colorful exit message with separator
            print(f"\n\033[36m{separator}\033[0m")
            print(f"\033[36m← \033[1;37mExited Shell\033[0m")
            print(f"\033[2mPress \033[0m\033[1;32mEnter\033[0m\033[2m to return to \033[0m\033[1;36mlazyk8s\033[0m\033[2m...\033[0m")
            print(f"\033[36m{separator}\033[0m")
            input()

        # Refresh the display after returning
        self.refresh_pods()
        if self.selected_pod:
            self.show_pod_info()
            self.show_pod_logs()

    def action_delete_pod(self) -> None:
        """Delete the selected pod after confirmation"""
        if not self.selected_pod:
            return

        pod_name = self.selected_pod.metadata.name
        namespace = self.k8s_client.get_current_namespace()

        def handle_confirmation(confirmed: bool) -> None:
            """Handle the confirmation response"""
            if confirmed:
                # Delete the pod
                success = self.k8s_client.delete_pod(pod_name)
                if success:
                    # Clear selection and refresh immediately
                    self.selected_pod = None
                    self.selected_container = None
                    self.refresh_pods()

                    # Schedule additional refreshes to show the replacement pod
                    self.set_timer(1.0, self.refresh_pods)
                    self.set_timer(3.0, self.refresh_pods)

        # Show confirmation dialog
        self.push_screen(
            ConfirmDialog(
                f"Delete pod [b]{pod_name}[/b] in namespace [b]{namespace}[/b]?\n\nThis action cannot be undone.",
                title="Confirm Pod Deletion"
            ),
            handle_confirmation
        )


class Gui:
    """GUI wrapper class"""

    def __init__(self, k8s_client: K8sClient, app_config: AppConfig):
        self.k8s_client = k8s_client
        self.app_config = app_config
        self.app = LazyK8sApp(k8s_client, app_config)

    def run(self) -> None:
        """Run the GUI application"""
        self.app.run()
