#!/usr/bin/env python3
"""
NetBox-EVE-NG Automation Orchestrator

This script:
1. Reads desired topology from topology.yml
2. Populates NetBox with devices, interfaces, IPs, and cables
3. Provisions EVE-NG lab based on NetBox data
4. Generates and pushes device configurations

Usage:
    python orchestrator.py --populate-netbox      # Populate NetBox with topology
    python orchestrator.py --provision-eveng      # Create EVE-NG lab from NetBox
    python orchestrator.py --configure-devices    # Push configs to devices
    python orchestrator.py --full                 # Do all of the above
"""

import argparse
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from scripts.netbox_client import NetBoxClient
from scripts.eveng_client import EVENGClient
from scripts.config_generator import ConfigGenerator
from scripts.device_configurator import DeviceConfigurator, vendor_to_netmiko_type

load_dotenv()

console = Console()


def require_env(name: str) -> str:
    """Read a required env var or exit with a clear message."""
    value = os.environ.get(name)
    if not value:
        console.print(
            f"[red]Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in, or pass via CLI flag.[/red]"
        )
        sys.exit(1)
    return value


def load_topology(topology_file: str = "topology.yml") -> dict:
    """Load topology definition from YAML file."""
    with open(topology_file, "r") as f:
        return yaml.safe_load(f)


def display_topology(topology: dict):
    """Display topology summary in a nice table."""
    console.print("\n[bold cyan]📋 Topology Summary[/bold cyan]\n")

    # Devices table
    table = Table(title="Devices")
    table.add_column("Name", style="cyan")
    table.add_column("Role", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Management IP", style="magenta")

    for device in topology.get("devices", []):
        mgmt_ip = "N/A"
        for iface in device.get("interfaces", []):
            if iface.get("mgmt"):
                mgmt_ip = iface.get("ip_address", "N/A")
                break
        table.add_row(
            device["name"],
            device["role"],
            device["device_type"],
            mgmt_ip
        )

    console.print(table)

    # Cables table
    table = Table(title="\nConnections")
    table.add_column("Device A", style="cyan")
    table.add_column("Interface A", style="green")
    table.add_column("", style="white")
    table.add_column("Device B", style="cyan")
    table.add_column("Interface B", style="green")

    for cable in topology.get("cables", []):
        table.add_row(
            cable["a_device"],
            cable["a_interface"],
            "↔",
            cable["b_device"],
            cable["b_interface"]
        )

    console.print(table)


def populate_netbox(topology: dict, netbox_url: str, netbox_token: str,
                    verify_ssl: bool = True):
    """Populate NetBox with topology data."""
    console.print("\n[bold green]📦 Populating NetBox...[/bold green]\n")

    client = NetBoxClient(netbox_url, netbox_token, verify_ssl=verify_ssl)

    with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
    ) as progress:
        # Create site
        task = progress.add_task("Creating site...", total=None)
        client.create_site(topology["site"])
        progress.update(task, description="✅ Site created")

        # Create device roles
        task = progress.add_task("Creating device roles...", total=None)
        for role in topology.get("device_roles", []):
            client.create_device_role(role)
        progress.update(task, description="✅ Device roles created")

        # Create manufacturers
        task = progress.add_task("Creating manufacturers...", total=None)
        for manufacturer in topology.get("manufacturers", []):
            client.create_manufacturer(manufacturer)
        progress.update(task, description="✅ Manufacturers created")

        # Create device types
        task = progress.add_task("Creating device types...", total=None)
        for device_type in topology.get("device_types", []):
            client.create_device_type(device_type)
        progress.update(task, description="✅ Device types created")

        # Create devices
        task = progress.add_task("Creating devices...", total=None)
        for device in topology.get("devices", []):
            client.create_device(device, topology)
        progress.update(task, description="✅ Devices created")

        # Create interfaces and IPs
        task = progress.add_task("Creating interfaces and IPs...", total=None)
        for device in topology.get("devices", []):
            for interface in device.get("interfaces", []):
                client.create_interface(device["name"], interface)
                if interface.get("ip_address"):
                    client.create_ip_address(device["name"], interface)
        progress.update(task, description="✅ Interfaces and IPs created")

        # Create cables
        task = progress.add_task("Creating cables...", total=None)
        for cable in topology.get("cables", []):
            client.create_cable(cable)
        progress.update(task, description="✅ Cables created")

    console.print("\n[bold green]✅ NetBox population complete![/bold green]")


def provision_eveng(netbox_url: str, netbox_token: str,
                    eveng_host: str, eveng_user: str, eveng_pass: str,
                    topology: dict, verify_ssl: bool = True):
    """Provision EVE-NG lab based on NetBox data."""
    console.print("\n[bold blue]🔧 Provisioning EVE-NG...[/bold blue]\n")

    netbox = NetBoxClient(netbox_url, netbox_token, verify_ssl=verify_ssl)
    eveng = EVENGClient(eveng_host, eveng_user, eveng_pass, verify_ssl=verify_ssl)

    # Get lab info from topology
    lab_info = topology["lab"]

    with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
    ) as progress:
        # Connect to EVE-NG
        task = progress.add_task("Connecting to EVE-NG...", total=None)
        eveng.connect()
        progress.update(task, description="✅ Connected to EVE-NG")

        # Create lab
        # Open existing lab (EVE-NG API has issues creating new labs)
        task = progress.add_task("Opening lab...", total=None)
        lab_path = f"/{lab_info['name']}.unl"
        eveng.open_lab(lab_path)
        progress.update(task, description=f"✅ Opened lab: {lab_path}")

        # Create management network
        task = progress.add_task("Creating management network...", total=None)
        mgmt_net = topology["management_network"]
        eveng.create_network(lab_path, mgmt_net["name"], mgmt_net["type"])
        progress.update(task, description="✅ Management network created")

        # Get devices from NetBox
        task = progress.add_task("Fetching devices from NetBox...", total=None)
        devices = netbox.get_devices()
        progress.update(task, description=f"✅ Found {len(devices)} devices in NetBox")

        # Create nodes in EVE-NG
        node_ids = {}
        for device in devices:
            task = progress.add_task(f"Creating node {device['name']}...", total=None)

            # Get device type info for EVE-NG template
            device_type_info = next(
                (dt for dt in topology["device_types"]
                 if dt["slug"] == device["device_type"]["slug"]),
                None
            )

            if device_type_info:
                node_id = eveng.create_node(
                    lab_path=lab_path,
                    name=device["name"],
                    template=device_type_info["eveng_template"],
                    left=device.get("position", {}).get("left", 50),
                    top=device.get("position", {}).get("top", 50)
                )
                node_ids[device["name"]] = node_id
                progress.update(task, description=f"✅ Node {device['name']} created (ID: {node_id})")

        # Connect nodes to management network
        task = progress.add_task("Connecting nodes to management...", total=None)
        for device_name, node_id in node_ids.items():
            eveng.connect_node_to_network(lab_path, node_id, "0", "1")  # Gi0/0 to MGMT
        progress.update(task, description="✅ Management connections complete")

        # Create direct connections between nodes
        # Create direct connections between nodes
        task = progress.add_task("Creating inter-node connections...", total=None)

        # Use topology definition directly instead of NetBox cables
        for cable in topology.get("cables", []):
            a_device = cable["a_device"]
            a_iface = cable["a_interface"]
            b_device = cable["b_device"]
            b_iface = cable["b_interface"]

            if a_device in node_ids and b_device in node_ids:
                eveng.connect_nodes(
                    lab_path,
                    node_ids[a_device], a_iface,
                    node_ids[b_device], b_iface
                )
        progress.update(task, description="✅ Inter-node connections complete")

        # Start all nodes
        task = progress.add_task("Starting all nodes...", total=None)
        eveng.start_all_nodes(lab_path)
        progress.update(task, description="✅ All nodes started")

    console.print("\n[bold blue]✅ EVE-NG provisioning complete![/bold blue]")
    console.print(f"[dim]Lab path: {lab_path}[/dim]")

    return lab_path, node_ids


def configure_devices(netbox_url: str, netbox_token: str, topology: dict,
                      verify_ssl: bool = True):
    """Generate and push device configurations."""
    console.print("\n[bold yellow]⚙️  Configuring devices...[/bold yellow]\n")

    netbox = NetBoxClient(netbox_url, netbox_token, verify_ssl=verify_ssl)
    config_gen = ConfigGenerator(topology)
    configurator = DeviceConfigurator()

    devices = netbox.get_devices()
    boot_timeout = int(os.environ.get("DEVICE_BOOT_TIMEOUT", "300"))

    with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
    ) as progress:
        for device in devices:
            task = progress.add_task(f"Configuring {device['name']}...", total=None)

            device_type = device.get("device_type") or {}
            manufacturer = device_type.get("manufacturer") or {}
            vendor = manufacturer.get("slug", "cisco") if isinstance(manufacturer, dict) else "cisco"
            netmiko_type = vendor_to_netmiko_type(vendor)

            interfaces = netbox.get_device_interfaces(device["name"])
            config = config_gen.generate_config(device, interfaces, vendor=vendor)

            mgmt_ip = None
            for iface in interfaces:
                if iface.get("description") == "Management":
                    ip_addr = netbox.get_interface_ip(device["name"], iface["name"])
                    if ip_addr:
                        mgmt_ip = ip_addr.split("/")[0]
                        break

            if not mgmt_ip:
                progress.update(task, description=f"⚠️  {device['name']} - no management IP")
                continue

            progress.update(task, description=f"Waiting for {device['name']} ({mgmt_ip}) on SSH...")
            if not configurator.wait_for_device(mgmt_ip, timeout=boot_timeout):
                progress.update(task, description=f"❌ {device['name']} unreachable after {boot_timeout}s")
                continue

            try:
                configurator.push_config(
                    host=mgmt_ip,
                    username=topology["device_defaults"]["username"],
                    password=topology["device_defaults"]["password"],
                    config=config,
                    device_type=netmiko_type,
                )
                progress.update(task, description=f"✅ {device['name']} configured ({netmiko_type})")
            except Exception as e:
                progress.update(task, description=f"❌ {device['name']} failed: {type(e).__name__}")

    console.print("\n[bold yellow]✅ Device configuration complete![/bold yellow]")


def main():
    parser = argparse.ArgumentParser(
        description="NetBox-EVE-NG Automation Orchestrator"
    )
    parser.add_argument("--topology", default="topology.yml",
                        help="Path to topology YAML file")
    parser.add_argument("--netbox-url", default=os.environ.get("NETBOX_URL"),
                        help="NetBox URL (env: NETBOX_URL)")
    parser.add_argument("--netbox-token", default=os.environ.get("NETBOX_TOKEN"),
                        help="NetBox API token (env: NETBOX_TOKEN)")
    parser.add_argument("--eveng-host", default=os.environ.get("EVENG_HOST"),
                        help="EVE-NG host (env: EVENG_HOST)")
    parser.add_argument("--eveng-user", default=os.environ.get("EVENG_USER"),
                        help="EVE-NG username (env: EVENG_USER)")
    parser.add_argument("--eveng-pass", default=os.environ.get("EVENG_PASS"),
                        help="EVE-NG password (env: EVENG_PASS)")
    parser.add_argument("--insecure", action="store_true",
                        help="Disable TLS certificate verification (lab use only)")

    parser.add_argument("--populate-netbox", action="store_true",
                        help="Populate NetBox with topology")
    parser.add_argument("--provision-eveng", action="store_true",
                        help="Provision EVE-NG from NetBox")
    parser.add_argument("--configure-devices", action="store_true",
                        help="Configure devices")
    parser.add_argument("--full", action="store_true",
                        help="Run full automation pipeline")
    parser.add_argument("--show-topology", action="store_true",
                        help="Display topology and exit")

    args = parser.parse_args()
    verify_ssl = not args.insecure

    # Load topology
    topology = load_topology(args.topology)

    if args.show_topology:
        display_topology(topology)
        return

    if not any([args.populate_netbox, args.provision_eveng,
                args.configure_devices, args.full]):
        parser.print_help()
        return

    needs_netbox = args.populate_netbox or args.provision_eveng or args.configure_devices or args.full
    needs_eveng = args.provision_eveng or args.full

    if needs_netbox and not args.netbox_url:
        console.print("[red]--netbox-url or NETBOX_URL is required[/red]")
        sys.exit(1)
    if needs_netbox and not args.netbox_token:
        console.print("[red]--netbox-token or NETBOX_TOKEN is required[/red]")
        sys.exit(1)
    if needs_eveng and not all([args.eveng_host, args.eveng_user, args.eveng_pass]):
        console.print("[red]--eveng-host/--eveng-user/--eveng-pass (or EVENG_* env) are required[/red]")
        sys.exit(1)

    console.print("[bold]🚀 NetBox-EVE-NG Automation Orchestrator[/bold]\n")
    display_topology(topology)

    if args.full or args.populate_netbox:
        populate_netbox(topology, args.netbox_url, args.netbox_token,
                        verify_ssl=verify_ssl)

    if args.full or args.provision_eveng:
        provision_eveng(
            args.netbox_url, args.netbox_token,
            args.eveng_host, args.eveng_user, args.eveng_pass,
            topology, verify_ssl=verify_ssl
        )

    if args.full or args.configure_devices:
        configure_devices(args.netbox_url, args.netbox_token, topology,
                          verify_ssl=verify_ssl)

    console.print("\n[bold green]🎉 Automation complete![/bold green]")


if __name__ == "__main__":
    main()