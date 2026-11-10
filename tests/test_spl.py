import pytest

from bastion.realism.spl import QueryError, run

EVENTS = [
    {"_time": "2026-11-10T09:00:01", "index": "security", "EventCode": 4625, "user": "maria", "src_ip": "203.0.113.45", "_raw": "An account failed to log on. Account Name: maria"},
    {"_time": "2026-11-10T09:00:02", "index": "security", "EventCode": 4625, "user": "jacob", "src_ip": "203.0.113.45", "_raw": "An account failed to log on. Account Name: jacob"},
    {"_time": "2026-11-10T09:00:03", "index": "security", "EventCode": 4625, "user": "emily", "src_ip": "203.0.113.45", "_raw": "An account failed to log on. Account Name: emily"},
    {"_time": "2026-11-10T09:00:04", "index": "security", "EventCode": 4624, "user": "emily", "src_ip": "203.0.113.45", "_raw": "An account was successfully logged on. Account Name: emily"},
    {"_time": "2026-11-10T09:30:00", "index": "security", "EventCode": 4625, "user": "george", "src_ip": "10.10.20.14", "_raw": "An account failed to log on. Account Name: george"},
    {"_time": "2026-11-10T10:00:00", "index": "sysmon", "EventCode": 1, "user": "emily", "Image": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "CommandLine": "powershell -nop -enc SQBFAFgA", "_raw": "Process Create: powershell -nop -enc SQBFAFgA"},
    {"_time": "2026-11-10T11:00:00", "index": "firewall", "action": "allowed", "src_ip": "10.10.1.20", "dest_ip": "203.0.113.45", "bytes_out": 98000000, "_raw": "ALLOW TCP 10.10.1.20 -> 203.0.113.45:443 bytes=98000000"},
]


def test_field_filters_and_wildcards():
    assert run(EVENTS, "index=security EventCode=4625")["total"] == 4
    assert run(EVENTS, "user=j*")["total"] == 1
    assert run(EVENTS, "EventCode=4625 src_ip!=203.0.113.45")["total"] == 1
    assert run(EVENTS, "index=security NOT user=emily")["total"] == 3


def test_free_text_and_or():
    assert run(EVENTS, '"-enc"')["total"] == 1
    assert run(EVENTS, "index=sysmon OR index=firewall")["total"] == 2


def test_stats_count_by_and_sort():
    result = run(EVENTS, "index=security EventCode=4625 | stats count by src_ip | sort -count")
    assert result["rows"][0] == {"src_ip": "203.0.113.45", "count": 3}
    assert result["columns"] == ["src_ip", "count"]


def test_distinct_count_and_where_finds_password_spraying():
    result = run(EVENTS, "EventCode=4625 | stats dc(user) as users by src_ip | where users > 2")
    assert result["rows"] == [{"src_ip": "203.0.113.45", "users": 3}]


def test_numeric_comparison_finds_big_uploads():
    assert run(EVENTS, "index=firewall bytes_out>50000000")["total"] == 1


def test_table_head_dedup_rename_top():
    rows = run(EVENTS, "index=security | dedup user | table user src_ip | head 2")["rows"]
    assert len(rows) == 2 and set(rows[0]) == {"user", "src_ip"}
    renamed = run(EVENTS, "EventCode=4624 | table user src_ip | rename src_ip as attacker")
    assert renamed["rows"][0]["attacker"] == "203.0.113.45" and "attacker" in renamed["columns"]
    top = run(EVENTS, "index=security | top src_ip")["rows"]
    assert top[0]["src_ip"] == "203.0.113.45" and top[0]["percent"] == 80.0


def test_helpful_errors():
    for bad in ("", "index=security | frobnicate", "index=security | stats", "| stats avg by user", 'user="maria'):
        with pytest.raises(QueryError):
            run(EVENTS, bad)
