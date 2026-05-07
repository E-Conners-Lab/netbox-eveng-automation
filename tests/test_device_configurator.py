"""Unit tests for device_configurator helpers."""

import pytest

from scripts.device_configurator import (
    VENDOR_TO_NETMIKO,
    BulkConfigurator,
    DeviceConfigurator,
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


@pytest.mark.unit
class TestBulkConfiguratorVendorMapping:
    """BulkConfigurator should resolve netmiko types from NetBox-shaped dicts."""

    def test_resolves_cisco_from_nested_manufacturer(self) -> None:
        bulk = BulkConfigurator(DeviceConfigurator())
        device = {"device_type": {"manufacturer": {"slug": "cisco"}}}
        assert bulk._get_netmiko_device_type(device) == "cisco_ios"

    def test_resolves_juniper_from_nested_manufacturer(self) -> None:
        bulk = BulkConfigurator(DeviceConfigurator())
        device = {"device_type": {"manufacturer": {"slug": "juniper"}}}
        assert bulk._get_netmiko_device_type(device) == "juniper_junos"

    def test_resolves_arista_from_nested_manufacturer(self) -> None:
        bulk = BulkConfigurator(DeviceConfigurator())
        device = {"device_type": {"manufacturer": {"slug": "arista"}}}
        assert bulk._get_netmiko_device_type(device) == "arista_eos"

    def test_defaults_to_cisco_when_manufacturer_missing(self) -> None:
        bulk = BulkConfigurator(DeviceConfigurator())
        assert bulk._get_netmiko_device_type({}) == "cisco_ios"
