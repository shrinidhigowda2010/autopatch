"""Edge-case tests for the bugs we know how to describe.

Each generated test has a normal case, a boundary (min or max) and an invalid
case. The names say which is which so the UI can show them.
"""

from __future__ import annotations

from app.analysis.findings import Finding


def render_tests(findings: list[Finding], only: Finding | None = None) -> str:
    chosen = findings if only is None else [only]
    blocks = ["import pytest"]
    seen: set[tuple] = set()
    for finding in chosen:
        if finding.category == "style" or finding.severity == "low":
            continue
        key = (finding.rule_id, finding.symbol, finding.file)
        if key in seen:
            continue
        seen.add(key)
        block = _one(finding)
        if block:
            blocks.append(block)
    if len(blocks) == 1:
        blocks.append("def test_no_actionable_bug():\n    assert True")
    return "\n\n".join(blocks) + "\n"


def _one(finding: Finding) -> str:
    rule = finding.rule_id
    symbol = finding.symbol or "fn"
    module = finding.file.rsplit("/", 1)[-1].removesuffix(".py")
    slug = f"{rule}_{symbol}"
    if rule == "marks_out_of_range":
        return f'''
def test_{slug}_normal():
    from {module} import {symbol}
    result = {symbol}([80, 90])
    assert result["percentage"] == 85

def test_{slug}_min_boundary():
    from {module} import {symbol}
    assert {symbol}([0])["percentage"] == 0

def test_{slug}_max_boundary():
    from {module} import {symbol}
    assert {symbol}([100])["percentage"] == 100

def test_{slug}_invalid_negative():
    from {module} import {symbol}
    with pytest.raises(ValueError):
        {symbol}([-5])

def test_{slug}_invalid_above_max():
    from {module} import {symbol}
    with pytest.raises(ValueError):
        {symbol}([150])
'''
    if rule == "empty_collection_divisor" and symbol == "mean":
        return f'''
def test_{slug}_normal():
    from {module} import mean
    assert mean([10, 20]) == 15

def test_{slug}_min_one():
    from {module} import mean
    assert mean([4]) == 4

def test_{slug}_invalid_empty():
    from {module} import mean
    with pytest.raises(ValueError):
        mean([])
'''
    if rule == "empty_collection_divisor":
        return f'''
def test_{slug}_normal():
    from {module} import {symbol}
    assert {symbol}([40, 60])["percentage"] == 50

def test_{slug}_invalid_empty():
    from {module} import {symbol}
    with pytest.raises(ValueError):
        {symbol}([])
'''
    if rule == "parameter_divisor":
        return f'''
def test_{slug}_normal():
    from {module} import {symbol}
    assert {symbol}(10, 2) == 5

def test_{slug}_min_zero_part():
    from {module} import {symbol}
    assert {symbol}(0, 5) == 0

def test_{slug}_max_large():
    from {module} import {symbol}
    assert {symbol}(1_000_000, 2) == 500_000

def test_{slug}_invalid_zero():
    from {module} import {symbol}
    with pytest.raises(ValueError):
        {symbol}(1, 0)
'''
    if rule == "deposit_non_positive":
        return '''
def test_deposit_non_positive_normal():
    from bank import Account
    assert Account("Ada", 10).deposit(5) == 15

def test_deposit_non_positive_min_one():
    from bank import Account
    assert Account("Ada", 0).deposit(1) == 1

def test_deposit_non_positive_invalid_negative():
    from bank import Account
    with pytest.raises(ValueError):
        Account("Ada", 10).deposit(-5)

def test_deposit_non_positive_invalid_zero():
    from bank import Account
    with pytest.raises(ValueError):
        Account("Ada", 10).deposit(0)
'''
    if rule == "withdraw_overdraft":
        return '''
def test_withdraw_overdraft_normal():
    from bank import Account
    assert Account("Ada", 100).withdraw(40) == 60

def test_withdraw_overdraft_max_exact():
    from bank import Account
    assert Account("Ada", 30).withdraw(30) == 0

def test_withdraw_overdraft_invalid_too_much():
    from bank import Account
    with pytest.raises(ValueError):
        Account("Ada", 100).withdraw(150)

def test_withdraw_overdraft_invalid_negative():
    from bank import Account
    with pytest.raises(ValueError):
        Account("Ada", 100).withdraw(-1)
'''
    if rule == "sql_injection":
        return '''
import sqlite3

def _users():
    conn = sqlite3.connect(":memory:")
    conn.execute("create table users (id integer, username text, password text)")
    conn.execute("insert into users values (1, 'ada', 'secret')")
    return conn

def test_sql_injection_normal():
    from auth import login
    row = login(_users(), "ada", "secret")
    assert row is not None and row[1] == "ada"

def test_sql_injection_min_unknown():
    from auth import login
    assert login(_users(), "zed", "nope") is None

def test_sql_injection_invalid_payload():
    from auth import login
    assert login(_users(), "nobody' OR '1'='1", "nope") is None
'''
    if rule == "off_by_one_neighbor":
        return f'''
def test_{slug}_normal():
    from {module} import {symbol}
    assert {symbol}([1, 3, 5]) == [2, 4]

def test_{slug}_min_pair():
    from {module} import {symbol}
    assert {symbol}([2, 4]) == [3]

def test_{slug}_invalid_end_does_not_crash():
    from {module} import {symbol}
    {symbol}([1, 2, 3, 4])
'''
    if rule == "off_by_one_skip_first":
        return f'''
def test_{slug}_normal():
    from {module} import {symbol}
    assert {symbol}([{{"qty": 2}}, {{"qty": 3}}]) == 5

def test_{slug}_min_one_row():
    from {module} import {symbol}
    assert {symbol}([{{"qty": 4}}]) == 4

def test_{slug}_max_many():
    from {module} import {symbol}
    rows = [{{"qty": 1}}] * 40
    assert {symbol}(rows) == 40
'''
    if rule == "mutable_default_argument":
        return f'''
def test_{slug}_normal():
    from {module} import {symbol}
    assert {symbol}("pen", []) == ["pen"]

def test_{slug}_min_single_call():
    from {module} import {symbol}
    assert {symbol}("a") == ["a"]

def test_{slug}_invalid_shared_default():
    from {module} import {symbol}
    {symbol}("a")
    assert {symbol}("b") == ["b"]
'''
    if rule == "hardcoded_secret":
        var = finding.symbol
        return f'''
import re
from pathlib import Path

def test_{slug}_normal_reads_environment():
    text = Path("{finding.file}").read_text(encoding="utf-8")
    assert 'os.environ.get("{var}"' in text

def test_{slug}_invalid_literal_removed():
    text = Path("{finding.file}").read_text(encoding="utf-8")
    assert not re.search(r"^{var}\\s*=\\s*['\\\"]", text, re.M)
'''
    return ""
