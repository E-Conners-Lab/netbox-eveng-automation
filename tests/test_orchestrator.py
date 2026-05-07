"""Unit tests for orchestrator helpers."""

from pathlib import Path

import pytest
import yaml

from orchestrator import load_topology, require_env


@pytest.mark.unit
class TestLoadTopology:
    def test_reads_yaml_into_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "topology.yml"
        path.write_text(
            yaml.safe_dump(
                {"lab": {"name": "test-lab"}, "devices": [{"name": "R1"}]}
            )
        )

        result = load_topology(str(path))

        assert result["lab"]["name"] == "test-lab"
        assert result["devices"][0]["name"] == "R1"


@pytest.mark.unit
class TestRequireEnv:
    def test_returns_value_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_TEST_VAR", "hello")
        assert require_env("MY_TEST_VAR") == "hello"

    def test_exits_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MY_TEST_VAR", raising=False)
        with pytest.raises(SystemExit) as exc:
            require_env("MY_TEST_VAR")
        assert exc.value.code == 1

    def test_exits_when_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MY_TEST_VAR", "")
        with pytest.raises(SystemExit):
            require_env("MY_TEST_VAR")
