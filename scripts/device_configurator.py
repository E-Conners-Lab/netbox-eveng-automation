#!/usr/bin/env python3
"""
Device Configurator

Pushes configurations to network devices using:
- Netmiko (SSH/CLI)
- NAPALM (multi-vendor abstraction)
- NETCONF (ncclient)
"""

import time
from typing import Optional
from netmiko import ConnectHandler
from netmiko.exceptions import NetMikoTimeoutException, AuthenticationException
from rich.console import Console

console = Console()


class DeviceConfigurator:
    """Push configurations to network devices."""
    
    def __init__(self):
        """Initialize the configurator."""
        self.connections = {}
    
    def wait_for_device(self, host: str, port: int = 22,
                        timeout: int = 300, interval: int = 10) -> bool:
        """Wait for a device to become reachable."""
        import socket
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    console.print(f"[green]Device {host} is reachable[/green]")
                    return True
            except socket.error:
                pass
            
            console.print(f"[dim]Waiting for {host}... ({int(time.time() - start_time)}s)[/dim]")
            time.sleep(interval)
        
        return False
    
    def push_config(self, host: str, username: str, password: str,
                    config: str, device_type: str = "cisco_ios",
                    enable_secret: Optional[str] = None) -> bool:
        """Push configuration to a device using Netmiko."""
        device = {
            "device_type": device_type,
            "host": host,
            "username": username,
            "password": password,
            "timeout": 60,
            "session_timeout": 60,
        }
        
        if enable_secret:
            device["secret"] = enable_secret
        
        try:
            console.print(f"[dim]Connecting to {host}...[/dim]")
            connection = ConnectHandler(**device)
            
            if enable_secret:
                connection.enable()
            
            # Send config
            console.print(f"[dim]Sending configuration to {host}...[/dim]")
            output = connection.send_config_set(
                config.split("\n"),
                delay_factor=2
            )
            
            # Save config
            connection.save_config()
            
            connection.disconnect()
            
            console.print(f"[green]Configuration pushed to {host}[/green]")
            return True
            
        except NetMikoTimeoutException:
            console.print(f"[red]Timeout connecting to {host}[/red]")
            return False
        except AuthenticationException:
            console.print(f"[red]Authentication failed for {host}[/red]")
            return False
        except Exception as e:
            console.print(f"[red]Error configuring {host}: {e}[/red]")
            return False
    
    def push_config_netconf(self, host: str, username: str, password: str,
                            config: str, port: int = 830,
                            hostkey_verify: bool = True) -> bool:
        """Push configuration using NETCONF.

        Args:
            host: Target device IP or hostname.
            username: SSH username.
            password: SSH password.
            config: Configuration payload.
            port: NETCONF port.
            hostkey_verify: Verify SSH host key. Set False only for trusted lab nets.
        """
        from ncclient import manager
        from ncclient.operations import RPCError

        try:
            console.print(f"[dim]Connecting to {host} via NETCONF...[/dim]")

            with manager.connect(
                host=host,
                port=port,
                username=username,
                password=password,
                hostkey_verify=hostkey_verify,
                device_params={"name": "iosxe"}
            ) as m:
                config_xml = f"""
                <config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
                    {config}
                </config>
                """
                
                m.edit_config(target="running", config=config_xml)
                
                console.print(f"[green]NETCONF config pushed to {host}[/green]")
                return True
                
        except RPCError as e:
            console.print(f"[red]NETCONF RPC error for {host}: {e}[/red]")
            return False
        except Exception as e:
            console.print(f"[red]NETCONF error for {host}: {e}[/red]")
            return False
    
    def get_running_config(self, host: str, username: str, password: str,
                           device_type: str = "cisco_ios") -> Optional[str]:
        """Get running configuration from a device."""
        device = {
            "device_type": device_type,
            "host": host,
            "username": username,
            "password": password,
            "timeout": 30,
        }
        
        try:
            connection = ConnectHandler(**device)
            config = connection.send_command("show running-config")
            connection.disconnect()
            return config
        except Exception as e:
            console.print(f"[red]Error getting config from {host}: {e}[/red]")
            return None
    
    def verify_connectivity(self, host: str, username: str, password: str,
                            device_type: str = "cisco_ios") -> bool:
        """Verify we can connect to a device."""
        device = {
            "device_type": device_type,
            "host": host,
            "username": username,
            "password": password,
            "timeout": 10,
        }
        
        try:
            connection = ConnectHandler(**device)
            connection.disconnect()
            return True
        except Exception:
            return False
    
    def run_command(self, host: str, username: str, password: str,
                    command: str, device_type: str = "cisco_ios") -> Optional[str]:
        """Run a command on a device and return output."""
        device = {
            "device_type": device_type,
            "host": host,
            "username": username,
            "password": password,
            "timeout": 30,
        }
        
        try:
            connection = ConnectHandler(**device)
            output = connection.send_command(command)
            connection.disconnect()
            return output
        except Exception as e:
            console.print(f"[red]Error running command on {host}: {e}[/red]")
            return None


class BulkConfigurator:
    """Configure multiple devices in parallel or sequence."""
    
    def __init__(self, configurator: DeviceConfigurator):
        self.configurator = configurator
    
    def configure_all(self, devices: list, configs: dict,
                      username: str, password: str,
                      sequential: bool = True) -> dict:
        """Configure all devices."""
        results = {}
        
        for device in devices:
            name = device["name"]
            config = configs.get(name)
            
            if not config:
                console.print(f"[yellow]No config for {name}, skipping[/yellow]")
                results[name] = False
                continue
            
            # Get management IP
            mgmt_ip = None
            if device.get("primary_ip4"):
                mgmt_ip = str(device["primary_ip4"]["address"]).split("/")[0]
            
            if not mgmt_ip:
                console.print(f"[yellow]No management IP for {name}, skipping[/yellow]")
                results[name] = False
                continue
            
            # Wait for device to be ready
            if not self.configurator.wait_for_device(mgmt_ip, timeout=180):
                console.print(f"[red]Device {name} not reachable[/red]")
                results[name] = False
                continue
            
            # Determine device type for netmiko
            device_type = self._get_netmiko_device_type(device)
            
            # Push config
            success = self.configurator.push_config(
                host=mgmt_ip,
                username=username,
                password=password,
                config=config,
                device_type=device_type
            )
            
            results[name] = success
        
        return results
    
    def _get_netmiko_device_type(self, device: dict) -> str:
        """Map device manufacturer to Netmiko device type."""
        device_type = device.get("device_type", {})
        manufacturer = device_type.get("manufacturer", {})
        vendor = manufacturer.get("slug", "cisco")
        
        mapping = {
            "cisco": "cisco_ios",
            "juniper": "juniper_junos",
            "arista": "arista_eos",
        }
        
        return mapping.get(vendor, "cisco_ios")
