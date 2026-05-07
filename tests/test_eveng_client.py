"""Unit tests for EVENGClient pure helpers."""

import pytest

from scripts.eveng_client import EVENGClient


@pytest.fixture
def client() -> EVENGClient:
    return EVENGClient(
        host="eveng.example.com",
        username="admin",
        password="ignored",
        verify_ssl=False,
    )


@pytest.mark.unit
class TestGetInterfaceId:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("GigabitEthernet0/0", "0"),
            ("GigabitEthernet0/1", "1"),
            ("GigabitEthernet0/3", "3"),
            ("Gi0/2", "2"),
            ("eth0", "0"),
            ("eth7", "7"),
            ("Ethernet5", "5"),
            # Juniper-style names
            ("ge-0/0/0", "0"),
            ("ge-0/0/3", "3"),
            ("xe-0/0/1", "1"),
            ("et-0/0/2", "2"),
            ("fe-0/0/4", "4"),
        ],
    )
    def test_known_patterns(
        self, client: EVENGClient, name: str, expected: str
    ) -> None:
        assert client._get_interface_id(name) == expected

    def test_falls_back_to_trailing_digit(self, client: EVENGClient) -> None:
        assert client._get_interface_id("custom42") == "42"

    def test_returns_zero_when_no_digit_found(self, client: EVENGClient) -> None:
        assert client._get_interface_id("noNumbersHere") == "0"


@pytest.mark.unit
class TestInit:
    def test_constructs_https_base_url(self) -> None:
        client = EVENGClient("host.example.com", "u", "p")
        assert client.base_url == "https://host.example.com:443/api"

    def test_supports_http_protocol(self) -> None:
        client = EVENGClient("host.example.com", "u", "p", protocol="http", port=80)
        assert client.base_url == "http://host.example.com:80/api"

    def test_verify_ssl_default_true(self) -> None:
        client = EVENGClient("host.example.com", "u", "p")
        assert client.session.verify is True

    def test_verify_ssl_disabled_when_requested(self) -> None:
        client = EVENGClient("host.example.com", "u", "p", verify_ssl=False)
        assert client.session.verify is False
