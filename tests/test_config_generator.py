"""Unit tests for ConfigGenerator filters and rendering."""

import pytest

from scripts.config_generator import ConfigGenerator


@pytest.fixture
def generator() -> ConfigGenerator:
    topology = {
        "device_defaults": {
            "domain": "example.lab",
            "username": "admin",
            "password": "lab",
            "enable_secret": "lab",
            "ssh_enabled": True,
            "netconf_enabled": True,
            "ntp_server": "192.0.2.1",
        },
        "management_network": {"gateway": "192.0.2.1"},
        "devices": [
            {
                "name": "R1",
                "interfaces": [
                    {
                        "name": "GigabitEthernet0/0",
                        "ip_address": "192.0.2.10/24",
                        "description": "Management",
                    }
                ],
            }
        ],
    }
    return ConfigGenerator(topology)


@pytest.mark.unit
class TestFilterIPAddress:
    def test_strips_cidr_suffix(self, generator: ConfigGenerator) -> None:
        assert generator._filter_ip_address("192.0.2.1/24") == "192.0.2.1"

    def test_passes_through_bare_ip(self, generator: ConfigGenerator) -> None:
        assert generator._filter_ip_address("10.0.0.1") == "10.0.0.1"


@pytest.mark.unit
class TestFilterNetmask:
    @pytest.mark.parametrize(
        "cidr,expected",
        [
            ("192.0.2.1/24", "255.255.255.0"),
            ("192.0.2.1/30", "255.255.255.252"),
            ("10.0.0.1/8", "255.0.0.0"),
            ("172.16.0.1/16", "255.255.0.0"),
            ("192.0.2.1/32", "255.255.255.255"),
        ],
    )
    def test_converts_prefix_to_netmask(
        self, generator: ConfigGenerator, cidr: str, expected: str
    ) -> None:
        assert generator._filter_netmask(cidr) == expected

    def test_default_when_no_prefix(self, generator: ConfigGenerator) -> None:
        assert generator._filter_netmask("192.0.2.1") == "255.255.255.0"


@pytest.mark.unit
class TestFilterJuniperInterface:
    def test_converts_gigabitethernet(self, generator: ConfigGenerator) -> None:
        assert generator._filter_juniper_interface("GigabitEthernet0/0") == "ge-0/0/0"
        assert generator._filter_juniper_interface("GigabitEthernet1/3") == "ge-1/0/3"

    def test_passes_through_unknown_format(self, generator: ConfigGenerator) -> None:
        assert generator._filter_juniper_interface("ge-0/0/0") == "ge-0/0/0"


@pytest.mark.unit
class TestGenerateConfig:
    def test_renders_cisco_hostname_and_interface(
        self, generator: ConfigGenerator
    ) -> None:
        device = {"name": "R1"}
        interfaces = [{"name": "GigabitEthernet0/0"}]

        config = generator.generate_config(device, interfaces, vendor="cisco")

        assert "hostname R1" in config
        assert "interface GigabitEthernet0/0" in config
        assert "192.0.2.10" in config
        assert "255.255.255.0" in config

    def test_renders_juniper_root_authentication(
        self, generator: ConfigGenerator
    ) -> None:
        device = {"name": "R1"}
        interfaces = [{"name": "GigabitEthernet0/0"}]

        config = generator.generate_config(device, interfaces, vendor="juniper")

        assert "host-name R1" in config
        assert "ge-0/0/0" in config

    def test_falls_back_to_cisco_for_unknown_vendor(
        self, generator: ConfigGenerator
    ) -> None:
        device = {"name": "R1"}
        config = generator.generate_config(device, [], vendor="mystery-vendor")
        assert "hostname R1" in config
