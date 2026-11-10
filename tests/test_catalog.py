import pytest

from bastion.catalog import TACTICS, CatalogError, load_catalog, validate


@pytest.fixture
def catalog():
    return load_catalog()


def test_catalog_loads(catalog):
    assert "phishing" in catalog.attacks
    assert "mfa" in catalog.defenses


def test_every_tactic_has_an_attack(catalog):
    for tactic in TACTICS:
        assert catalog.attacks_in_tactic(tactic), f"No attack for tactic '{tactic}'"


def test_every_attack_has_a_counter(catalog):
    for attack_id in catalog.attacks:
        assert catalog.defenses_against(attack_id), f"Nothing defends against '{attack_id}'"


def test_mitre_url(catalog):
    assert catalog.attacks["brute-force"].mitre_url == "https://attack.mitre.org/techniques/T1110/001/"


def test_all_defenses_cost_more_than_the_budget(catalog):
    total = sum(defense.cost for defense in catalog.defenses.values())
    assert total > 100


def test_invalid_mitre_id_is_rejected(catalog):
    catalog.attacks["phishing"].mitre_id = "phishing"
    with pytest.raises(CatalogError):
        validate(catalog)


def test_defense_against_unknown_attack_is_rejected(catalog):
    catalog.defenses["mfa"].blocks["time-travel"] = 0.5
    with pytest.raises(CatalogError):
        validate(catalog)
