import pytest

from bastion.catalog import DATA_DIR
from bastion.waf import RuleError, evaluate, evaluate_safely, load_corpus, load_rules, normalize, parse_rules


def test_normalizing_undoes_common_tricks():
    assert normalize("%2527%2520OR", ["url-decode"]) == "' OR"
    assert normalize("&lt;script&gt;", ["html-decode"]) == "<script>"
    assert normalize("1/**/UNION/**/SELECT", ["strip-sql-comments", "collapse-spaces", "lowercase"]) == "1 union select"


def test_starter_rules_catch_most_but_not_all():
    report = evaluate(load_rules(DATA_DIR / "waf_starter.json"), load_corpus())
    assert 0.7 < report.catch_rate < 1
    assert report.missed and len(report.false_positives) == 1


def test_no_rules_block_nothing():
    report = evaluate(parse_rules({"rules": []}), load_corpus())
    assert report.catch_rate == 0 and report.score == 0


def test_blocking_everything_is_punished():
    report = evaluate(parse_rules({"rules": [{"id": "all", "pattern": "."}]}), load_corpus())
    assert report.catch_rate == 1
    assert report.score == 0


def test_bad_regex_and_unknown_step_are_explained():
    with pytest.raises(RuleError):
        parse_rules({"rules": [{"id": "broken", "pattern": "(unclosed"}]})
    with pytest.raises(RuleError):
        parse_rules({"normalize": ["magic"], "rules": []})


def test_catastrophic_regex_is_stopped():
    corpus = {"attacks": [{"kind": "sqli", "text": "a" * 40 + "!", "trick": "redos"}], "benign": []}
    rules = parse_rules({"rules": [{"id": "evil", "pattern": "^(a+)+$"}]})
    with pytest.raises(RuleError, match="ReDoS"):
        evaluate_safely(rules, corpus, timeout=1)
