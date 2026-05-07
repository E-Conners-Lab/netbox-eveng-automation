#!/usr/bin/env python3
"""
EVE-NG API Client

Handles all interactions with EVE-NG for:
- Creating labs
- Adding nodes
- Creating networks
- Connecting nodes
- Starting/stopping nodes
"""

import re
import requests
from rich.console import Console

console = Console()


class EVENGClient:
    """Client for interacting with EVE-NG API."""

    def __init__(self, host: str, username: str, password: str,
                 protocol: str = "https", port: int = 443,
                 verify_ssl: bool = True):
        """Initialize EVE-NG connection parameters.

        Args:
            host: EVE-NG hostname or IP.
            username: API username.
            password: API password.
            protocol: http or https.
            port: API port.
            verify_ssl: Verify TLS certs. Set False only for self-signed lab use.
        """
        self.base_url = f"{protocol}://{host}:{port}/api"
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.connected = False
        if not verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def connect(self) -> bool:
        """Authenticate with EVE-NG."""
        login_url = f"{self.base_url}/auth/login"

        response = self.session.post(
            login_url,
            json={
                "username": self.username,
                "password": self.password,
                "html5": 1
            }
        )

        if response.status_code == 200:
            self.connected = True
            return True
        else:
            raise ConnectionError(f"Failed to connect to EVE-NG: {response.text}")

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make authenticated request to EVE-NG API."""
        if not self.connected:
            self.connect()

        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)

        # Handle session timeout
        if response.status_code == 412:
            self.connect()
            response = self.session.request(method, url, **kwargs)

        if response.text:
            try:
                return response.json()
            except ValueError:
                return {"status": "error", "message": response.text}
        return {}

    def open_lab(self, lab_path: str) -> bool:
        """Open a lab for editing."""
        result = self._request("GET", f"/labs{lab_path}")
        return result.get("status") == "success"

    def create_lab(self, name: str, description: str = "",
                   author: str = "", version: str = "1", path: str = "/") -> str:
        """Create a new lab."""
        # Clean lab name for path
        clean_name = re.sub(r'[^a-zA-Z0-9_-]', '-', name)

        data = {
            "name": name,
            "path": path,
            "description": description,
            "author": author,
            "version": version,
            "scripttimeout": 600
        }

        result = self._request("POST", "/labs", json=data)

        if result.get("status") == "success":
            return f"/{clean_name}.unl"
        else:
            console.print(f"[dim]Lab may already exist, attempting to use existing[/dim]")
            return f"/{clean_name}.unl"

    def delete_lab(self, lab_path: str) -> bool:
        """Delete a lab."""
        result = self._request("DELETE", f"/labs{lab_path}")
        return result.get("status") == "success"

    def create_network(self, lab_path: str, name: str,
                       network_type: str = "bridge",
                       left: int = 50, top: int = 50) -> str:
        """Create a network in a lab."""
        # Open lab first
        self.open_lab(lab_path)

        data = {
            "name": name,
            "type": network_type,
            "left": left,
            "top": top,
            "visibility": 1
        }

        result = self._request(
            "POST",
            f"/labs{lab_path}/networks",
            json=data
        )

        if result.get("status") == "success":
            return str(result.get("data", {}).get("id"))
        return None

    def create_node(self, lab_path: str, name: str, template: str,
                    left: int = 50, top: int = 50,
                    cpu: int = 1, ram: int = 512,
                    ethernet: int = 4) -> str:
        """Create a node in a lab."""
        # Open lab first
        self.open_lab(lab_path)

        data = {
            "name": name,
            "template": template,
            "type": "qemu",
            "left": left,
            "top": top,
            "cpu": cpu,
            "ram": ram,
            "ethernet": ethernet,
            "console": "telnet",
            "config": "Unconfigured",
            "delay": 0
        }

        result = self._request(
            "POST",
            f"/labs{lab_path}/nodes",
            json=data
        )

        if result.get("status") == "success":
            node_id = result.get("data", {}).get("id")
            console.print(f"[green]Node {name} created with ID {node_id}[/green]")
            return str(node_id)

        console.print(f"[red]Node creation failed: {result}[/red]")
        return None

    def get_node_interfaces(self, lab_path: str, node_id: str) -> list:
        """Get interfaces for a node."""
        result = self._request(
            "GET",
            f"/labs{lab_path}/nodes/{node_id}/interfaces"
        )

        if result.get("status") == "success":
            data = result.get("data", {})
            return data.get("ethernet", {})
        return {}

    def connect_node_to_network(self, lab_path: str, node_id: str,
                                interface_id: str, network_id: str) -> bool:
        """Connect a node interface to a network."""
        # Open lab first
        self.open_lab(lab_path)

        data = {
            f"{interface_id}": network_id
        }

        result = self._request(
            "PUT",
            f"/labs{lab_path}/nodes/{node_id}/interfaces",
            json=data
        )

        if result.get("status") != "success":
            console.print(
                f"[red]Failed to connect node {node_id} iface {interface_id} to network {network_id}: {result}[/red]")
            return False
        return True

    def connect_nodes(self, lab_path: str,
                      src_node_id: str, src_interface: str,
                      dst_node_id: str, dst_interface: str) -> bool:
        """Connect two nodes together directly."""
        # Open lab first
        self.open_lab(lab_path)

        # Create a bridge network for this connection
        network_name = f"p2p-{src_node_id}-{dst_node_id}"
        network_id = self.create_network(lab_path, network_name, "bridge")

        if not network_id:
            console.print(f"[red]Failed to create network {network_name}[/red]")
            return False

        console.print(f"[dim]Created network {network_name} with ID {network_id}[/dim]")

        # Map interface names to IDs
        src_iface_id = self._get_interface_id(src_interface)
        dst_iface_id = self._get_interface_id(dst_interface)

        console.print(
            f"[dim]Connecting {src_node_id}:{src_iface_id} and {dst_node_id}:{dst_iface_id} to network {network_id}[/dim]")

        # Connect both nodes to this network
        result1 = self.connect_node_to_network(lab_path, src_node_id, src_iface_id, network_id)
        result2 = self.connect_node_to_network(lab_path, dst_node_id, dst_iface_id, network_id)

        return result1 and result2

    def _get_interface_id(self, interface_name: str) -> str:
        """Convert interface name to EVE-NG interface ID."""
        # Match Juniper-style names first (ge-0/0/3, xe-0/0/0, et-0/0/0,
        # fe-0/0/0, me-0/0/0, fxp-0/0/0) and extract the port number.
        patterns = [
            (r'(?:ge|xe|et|fe|me|fxp)-\d+/\d+/(\d+)', lambda m: m.group(1)),
            (r'GigabitEthernet0/(\d+)', lambda m: m.group(1)),
            (r'Gi0/(\d+)', lambda m: m.group(1)),
            (r'eth(\d+)', lambda m: m.group(1)),
            (r'Ethernet(\d+)', lambda m: m.group(1)),
        ]

        for pattern, extractor in patterns:
            match = re.match(pattern, interface_name)
            if match:
                return extractor(match)

        # Try to extract the last number
        match = re.search(r'(\d+)$', interface_name.replace("/", ""))
        if match:
            return match.group(1)

        return "0"

    def start_node(self, lab_path: str, node_id: str) -> bool:
        """Start a specific node."""
        self.open_lab(lab_path)
        result = self._request(
            "GET",
            f"/labs{lab_path}/nodes/{node_id}/start"
        )
        return result.get("status") == "success"

    def stop_node(self, lab_path: str, node_id: str) -> bool:
        """Stop a specific node."""
        self.open_lab(lab_path)
        result = self._request(
            "GET",
            f"/labs{lab_path}/nodes/{node_id}/stop"
        )
        return result.get("status") == "success"

    def start_all_nodes(self, lab_path: str) -> bool:
        """Start all nodes in a lab."""
        self.open_lab(lab_path)
        result = self._request(
            "GET",
            f"/labs{lab_path}/nodes/start"
        )
        return result.get("status") == "success"

    def stop_all_nodes(self, lab_path: str) -> bool:
        """Stop all nodes in a lab."""
        self.open_lab(lab_path)
        result = self._request(
            "GET",
            f"/labs{lab_path}/nodes/stop"
        )
        return result.get("status") == "success"

    def get_node_status(self, lab_path: str, node_id: str) -> dict:
        """Get status of a node."""
        result = self._request(
            "GET",
            f"/labs{lab_path}/nodes/{node_id}"
        )

        if result.get("status") == "success":
            return result.get("data", {})
        return {}

    def get_lab_nodes(self, lab_path: str) -> dict:
        """Get all nodes in a lab."""
        result = self._request(
            "GET",
            f"/labs{lab_path}/nodes"
        )

        if result.get("status") == "success":
            return result.get("data", {})
        return {}

    def wipe_node(self, lab_path: str, node_id: str) -> bool:
        """Wipe a node (reset to factory)."""
        self.open_lab(lab_path)
        result = self._request(
            "GET",
            f"/labs{lab_path}/nodes/{node_id}/wipe"
        )
        return result.get("status") == "success"