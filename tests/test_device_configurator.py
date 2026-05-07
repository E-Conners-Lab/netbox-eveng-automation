"""Unit tests for device_configurator helpers."""

import pytest

from scripts.device_configurator import (
    VENDOR_TO_NETMIKO,
    vendor_to_netmiko_type,
)


@pytest.mark.unit
class TestVendorToNetmikoType:
    @pytest.mark.parametrize(
        "vendor,expected",
        [
            ("cisco", "cisco_ios"),
            ("juniper", "juniper_junos"),
            ("arista", "arista_eos"),
        ],
    )
    def test_known_vendors(self, vendor: str, expected: str) -> None:
        assert vendor_to_netmiko_type(vendor) == expected

    def test_unknown_vendor_falls_back_to_cisco(self) -> None:
        assert vendor_to_netmiko_type("nokia") == "cisco_ios"
        assert vendor_to_netmiko_type("") == "cisco_ios"

    def test_mapping_constant_matches_helper(self) -> None:
        for vendor, netmiko_type in VENDOR_TO_NETMIKO.items():
            assert vendor_to_netmiko_type(vendor) == netmiko_type
