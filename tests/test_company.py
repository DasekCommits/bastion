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


def test_awareness_must_be_in_range(company):
    company.employees[0].awareness = 1.5
    with pytest.raises(ScenarioError):
        validate(company)


def test_budgets_are_rolled_in_steps_of_five(company):
    import random

    from bastion.company import roll_mistakes

    rng = random.Random(3)
    blue = {roll_mistakes(company, rng).budget for _ in range(300)}
    red = {roll_mistakes(company, rng).red_budget for _ in range(300)}
    assert blue == {40, 45, 50, 55, 60}
    assert red == {40, 45, 50, 55, 60}


def test_budget_range_must_use_steps_of_five(company):
    company.budget_range = [42, 60]
    with pytest.raises(ScenarioError):
        validate(company)
