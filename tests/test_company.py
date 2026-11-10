import pytest

from bastion.company import ScenarioError, load_scenario, validate


@pytest.fixture
def company():
    return load_scenario("olive-byte")


def test_scenario_loads(company):
    assert company.name == "Olive Byte"
    assert company.tier == "small"


def test_internet_facing_servers(company):
    ids = [server.id for server in company.internet_facing_servers()]
    assert ids == ["web-01", "mail"]


def test_owner_is_admin(company):
    assert "maria" in [employee.id for employee in company.admins()]


def test_unknown_server_access_is_rejected(company):
    company.employees[0].access.append("does-not-exist")
    with pytest.raises(ScenarioError):
        validate(company)


def test_data_value_must_be_in_range(company):
    company.data[0].value = 42
    with pytest.raises(ScenarioError):
        validate(company)
