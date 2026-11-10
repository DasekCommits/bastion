import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BASTION_HOME", str(tmp_path / "bastion-home"))
