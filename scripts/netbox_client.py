#!/usr/bin/env python3
"""
NetBox API Client

Handles all interactions with NetBox for:
- Creating sites, device roles, manufacturers
- Creating device types and devices
- Creating interfaces and IP addresses
- Creating cables between devices
"""

import pynetbox
from rich.console import Console

console = Console()


class NetBoxClient:
    """Client for interacting with NetBox API."""

    def __init__(self, url: str, token: str, verify_ssl: bool = True):
        """Initialize NetBox connection.

        Args:
            url: NetBox base URL.
            token: API token.
            verify_ssl: Verify TLS certs. Set False only for self-signed lab use.
        """
        self.nb = pynetbox.api(url, token=token)
        self.nb.http_session.verify = verify_ssl
        if not verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def create_site(self, site_data: dict) -> dict:
        """Create a site in NetBox."""
        existing = self.nb.dcim.sites.get(slug=site_data["slug"])
        if existing:
            console.print(f"[dim]Site '{site_data['name']}' already exists[/dim]")
            return dict(existing)

        site = self.nb.dcim.sites.create(
            name=site_data["name"],
            slug=site_data["slug"],
            description=site_data.get("description", "")
        )
        return dict(site)

    def create_device_role(self, role_data: dict) -> dict:
        """Create a device role in NetBox."""
        existing = self.nb.dcim.device_roles.get(slug=role_data["slug"])
        if existing:
            console.print(f"[dim]Device role '{role_data['name']}' already exists[/dim]")
            return dict(existing)

        role = self.nb.dcim.device_roles.create(
            name=role_data["name"],
            slug=role_data["slug"],
            color=role_data.get("color", "000000")
        )
        return dict(role)

    def create_manufacturer(self, manufacturer_data: dict) -> dict:
        """Create a manufacturer in NetBox."""
        existing = self.nb.dcim.manufacturers.get(slug=manufacturer_data["slug"])
        if existing:
            console.print(f"[dim]Manufacturer '{manufacturer_data['name']}' already exists[/dim]")
            return dict(existing)

        manufacturer = self.nb.dcim.manufacturers.create(
            name=manufacturer_data["name"],
            slug=manufacturer_data["slug"]
        )
        return dict(manufacturer)

    def create_device_type(self, device_type_data: dict) -> dict:
        """Create a device type in NetBox."""
        existing = self.nb.dcim.device_types.get(slug=device_type_data["slug"])
        if existing:
            console.print(f"[dim]Device type '{device_type_data['model']}' already exists[/dim]")
            return dict(existing)

        # Get manufacturer
        manufacturer = self.nb.dcim.manufacturers.get(slug=device_type_data["manufacturer"])

        device_type = self.nb.dcim.device_types.create(
            manufacturer=manufacturer.id,
            model=device_type_data["model"],
            slug=device_type_data["slug"]
        )

        # Create interface templates
        for iface in device_type_data.get("interfaces", []):
            self.nb.dcim.interface_templates.create(
                device_type=device_type.id,
                name=iface["name"],
                type=iface["type"]
            )

        return dict(device_type)

    def create_device(self, device_data: dict, topology: dict) -> dict:
        """Create a device in NetBox."""
        existing = self.nb.dcim.devices.get(name=device_data["name"])
        if existing:
            console.print(f"[dim]Device '{device_data['name']}' already exists[/dim]")
            return dict(existing)

        # Get related objects
        site = self.nb.dcim.sites.get(slug=device_data["site"])
        device_type = self.nb.dcim.device_types.get(slug=device_data["device_type"])
        role = self.nb.dcim.device_roles.get(slug=device_data["role"])

        # Store position in custom fields or local context
        device = self.nb.dcim.devices.create(
            name=device_data["name"],
            site=site.id,
            device_type=device_type.id,
            role=role.id,
            status="active",
            local_context_data={
                "eveng_position": device_data.get("position", {"left": 50, "top": 50})
            }
        )

        return dict(device)

    def create_interface(self, device_name: str, interface_data: dict) -> dict:
        """Create an interface on a device."""
        device = self.nb.dcim.devices.get(name=device_name)
        if not device:
            raise ValueError(f"Device '{device_name}' not found")

        # Check if interface already exists
        existing = self.nb.dcim.interfaces.get(device_id=device.id, name=interface_data["name"])
        if existing:
            # Update description if needed
            if interface_data.get("description"):
                existing.description = interface_data["description"]
                existing.save()
            return dict(existing)

        interface = self.nb.dcim.interfaces.create(
            device=device.id,
            name=interface_data["name"],
            type="1000base-t",
            enabled=interface_data.get("enabled", True),
            description=interface_data.get("description", "")
        )

        return dict(interface)

    def create_ip_address(self, device_name: str, interface_data: dict) -> dict:
        """Create an IP address and assign to interface."""
        device = self.nb.dcim.devices.get(name=device_name)
        interface = self.nb.dcim.interfaces.get(device_id=device.id, name=interface_data["name"])

        if not interface:
            raise ValueError(f"Interface '{interface_data['name']}' not found on {device_name}")

        ip_address = interface_data.get("ip_address")
        if not ip_address:
            return None

        # Check if IP already exists
        existing = self.nb.ipam.ip_addresses.get(address=ip_address)
        if existing:
            console.print(f"[dim]IP '{ip_address}' already exists[/dim]")
            return dict(existing)

        ip = self.nb.ipam.ip_addresses.create(
            address=ip_address,
            assigned_object_type="dcim.interface",
            assigned_object_id=interface.id,
            status="active"
        )

        # If this is the management interface, set as primary
        if interface_data.get("mgmt"):
            device.primary_ip4 = ip.id
            device.save()

        return dict(ip)

    def create_cable(self, cable_data: dict) -> dict:
        """Create a cable between two interfaces."""
        # Get termination A
        device_a = self.nb.dcim.devices.get(name=cable_data["a_device"])
        iface_a = self.nb.dcim.interfaces.get(
            device_id=device_a.id,
            name=cable_data["a_interface"]
        )

        # Get termination B
        device_b = self.nb.dcim.devices.get(name=cable_data["b_device"])
        iface_b = self.nb.dcim.interfaces.get(
            device_id=device_b.id,
            name=cable_data["b_interface"]
        )

        # Check if cable already exists
        if iface_a.cable or iface_b.cable:
            console.print(
                f"[dim]Cable already exists between {cable_data['a_device']} and {cable_data['b_device']}[/dim]")
            return None

        cable = self.nb.dcim.cables.create(
            a_terminations=[{
                "object_type": "dcim.interface",
                "object_id": iface_a.id
            }],
            b_terminations=[{
                "object_type": "dcim.interface",
                "object_id": iface_b.id
            }],
            status="connected",
            label=cable_data.get("description", "")
        )

        return dict(cable)

    def get_devices(self) -> list:
        """Get all devices from NetBox."""
        devices = self.nb.dcim.devices.all()
        result = []
        for device in devices:
            dev_dict = dict(device)
            # Include position from local context
            if device.local_context_data:
                dev_dict["position"] = device.local_context_data.get("eveng_position", {})
            result.append(dev_dict)
        return result

    def get_device_interfaces(self, device_name: str) -> list:
        """Get all interfaces for a device."""
        device = self.nb.dcim.devices.get(name=device_name)
        if not device:
            return []

        interfaces = self.nb.dcim.interfaces.filter(device_id=device.id)
        return [dict(iface) for iface in interfaces]

    def get_interface_ip(self, device_name: str, interface_name: str) -> str:
        """Get IP address for a specific interface."""
        device = self.nb.dcim.devices.get(name=device_name)
        interface = self.nb.dcim.interfaces.get(device_id=device.id, name=interface_name)

        if not interface:
            return None

        ips = self.nb.ipam.ip_addresses.filter(interface_id=interface.id)
        for ip in ips:
            return str(ip.address)

        return None

    def get_cables(self) -> list:
        """Get all cables from NetBox."""
        cables = self.nb.dcim.cables.all()
        return [dict(cable) for cable in cables]