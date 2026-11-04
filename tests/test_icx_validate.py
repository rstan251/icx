#!/usr/bin/env python3
"""Plain-assert tests for icx_validate.py. Run: python3 tests/test_icx_validate.py
Copyright (c) 2026 Robert Stanley / Iron Noodle Technologies."""
import io
import os
import sys
import tempfile
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import icx_validate as V  # noqa: E402

CB = os.path.join(ROOT, "examples", "codebook.yaml")
IDX = os.path.join(ROOT, "examples", "index.yaml")
CL_EX = os.path.join(ROOT, "clients.example.yaml")
T = "#T-n"
results = []


def case(name):
    def deco(fn):
        try:
            fn()
            results.append((name, True, ""))
        except AssertionError as e:
            results.append((name, False, str(e)))
        except Exception as e:
            results.append((name, False, "%s: %s" % (type(e).__name__, e)))
        return fn
    return deco


def book():
    cb = V.load_yaml(CB)["icx"]
    errors = []
    out = V.collect_companies(cb, errors)
    assert not errors, errors
    return out


def run(clients=None, lines=None, outbound=False):
    return V.validate(
        CB, IDX, clients_path=clients, lines=lines, outbound=outbound,
    )


def hdr(client, verb="ASK", obj="pr.voice.intake~cfg", extra=""):
    tail = (" " + extra) if extra else ""
    return "@ENG>ICOM>OPS P1 %s %s %s %s%s" % (client, T, verb, obj, tail)


def out_tok(co="cogent-marketing", cl="abc", topic="voice-intake-config", icx="1.2.0"):
    return "co=%s cl=%s topic=%s icx=%s" % (co, cl, topic, icx)


def assert_ok(code, errors, warnings=None):
    assert code == 0, "expected OK got %s %s" % (code, errors)
    assert not errors, errors


def assert_why(errors, why):
    blob = " ".join(errors)
    assert why in blob, "expected %s in %s" % (why, errors)


# --- existing codebook + index (must keep passing) ---

@case("codebook-index-still-ok")
def _():
    code, errors, warnings, stats = run()
    assert_ok(code, errors)
    assert stats["codes"] >= 10
    assert stats["verbs"] == 10
    assert stats["index"] >= 1
    assert stats["companies"] == 3


@case("existing-object-codes-still-live")
def _():
    code, errors, warnings, stats = run()
    assert_ok(code, errors)
    cb = V.load_yaml(CB)["icx"]
    live = {c["code"] for c in cb["classes"]}
    live.update(c["code"] for c in cb["codes"])
    for need in (
        "org", "pr", "sys", "ops", "mk", "fin", "lg", "rs", "dt", "x",
        "pr.voice", "pr.voice.intake", "org.proto",
    ):
        assert need in live, need


@case("cli-two-arg-form-unchanged")
def _():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = V.main(CB, IDX)
    assert rc == 0, buf.getvalue()
    out = buf.getvalue()
    assert out.strip().startswith("OK:") or "\nOK:" in out, out
    assert "codes" in out and "verbs" in out


@case("companies-short-and-full")
def _():
    cb = V.load_yaml(CB)["icx"]
    assert cb["version"] == "1.2.0"
    by_short = {c["short"]: c for c in cb["companies"]}
    assert by_short["IN"]["full"] == "I-MD-XXXX"
    assert by_short["IN"]["name"] == "Iron Noodle LLC"
    assert by_short["IN"]["status"] == "unverified"
    assert by_short["CM"]["full"] == "C-TBD-XXXX"
    assert by_short["CM"]["status"] == "tbd"
    assert by_short["CD"]["full"] == "C-TBD-XXXX"
    assert by_short["CD"]["status"] == "tbd"
    assert by_short["CM"]["full"] == by_short["CD"]["full"]


# --- Rule 14a client slot: shorthand and full ---

@case("shorthand-company-dot-client-ok")
def _():
    code, errors, warnings, stats = run(clients=CL_EX, lines=[hdr("CM.ABC")])
    assert_ok(code, errors)
    p = stats["parsed"][0]
    assert p["company_short"] == "CM", p
    assert p["company_full"] == "C-TBD-XXXX", p
    assert p["client_short"] == "ABC", p
    assert p["client_id"] == "0000", p
    assert p["resolved"] == "C-TBD-XXXX.0000", p


@case("full-company-dot-client-ok")
def _():
    code, errors, warnings, stats = run(
        clients=CL_EX, lines=[hdr("C-TBD-XXXX.ABC")],
    )
    assert_ok(code, errors)
    p = stats["parsed"][0]
    assert p["company_full"] == "C-TBD-XXXX", p
    assert p["client_id"] == "0000", p


@case("bare-registered-client-expands")
def _():
    code, errors, warnings, stats = run(clients=CL_EX, lines=[hdr("ABC")])
    assert_ok(code, errors)
    p = stats["parsed"][0]
    assert p["company_short"] == "CM", p
    assert p["company_full"] == "C-TBD-XXXX", p
    assert p["client_id"] == "0000", p


@case("bare-xyz-ok")
def _():
    code, errors, warnings, _ = run(clients=CL_EX, lines=[hdr("XYZ")])
    assert_ok(code, errors)


@case("int0-under-any-company")
def _():
    for slot in ("IN.INT0", "CM.INT0", "CD.INT0", "INT0", "I-MD-XXXX.INT0"):
        code, errors, warnings, _ = run(
            clients=CL_EX, lines=[hdr(slot, verb="GO", obj="org.proto")],
        )
        assert_ok(code, errors)


@case("int0-default-is-in-int0")
def _():
    parsed, e, w = V.resolve_client_slot("INT0", book(), None)
    assert not e, e
    assert parsed["company_short"] == "IN", parsed
    assert parsed["company_full"] == "I-MD-XXXX", parsed
    assert parsed["resolved"] == "I-MD-XXXX.INT0", parsed


@case("company-shorthand-prefix-matches-all-clients")
def _():
    code, errors, warnings, stats = run(clients=CL_EX, lines=[hdr("CM")])
    assert_ok(code, errors)
    p = stats["parsed"][0]
    assert p["company_short"] == "CM", p
    assert p["company_full"] == "C-TBD-XXXX", p
    assert p["client_short"] is None, p


@case("expand-shorthand-in-to-full")
def _():
    parsed, e, w = V.resolve_client_slot("IN.INT0", book(), None)
    assert not e, e
    assert parsed["company_short"] == "IN"
    assert parsed["company_full"] == "I-MD-XXXX"
    assert parsed["resolved"] == "I-MD-XXXX.INT0"


@case("letter-c-alone-not-unique")
def _():
    code, errors, warnings, _ = run(clients=CL_EX, lines=[hdr("C.ABC")])
    assert code == 1
    assert_why(errors, "why=icx.co.unk")
    parsed, e, w = V.resolve_client_slot("C", book(), None)
    assert e and "why=icx.co.unk" in " ".join(e), e


@case("unknown-company-shorthand")
def _():
    code, errors, warnings, _ = run(clients=CL_EX, lines=[hdr("ZZ.ABC")])
    assert code == 1
    assert_why(errors, "why=icx.co.unk")


@case("unknown-client-with-registry")
def _():
    code, errors, warnings, _ = run(clients=CL_EX, lines=[hdr("CM.QQQ")])
    assert code == 1
    assert_why(errors, "why=icx.cl.unk")


@case("bare-unknown-client-with-registry")
def _():
    code, errors, warnings, _ = run(clients=CL_EX, lines=[hdr("QQQ")])
    assert code == 1
    assert_why(errors, "why=icx.cl.unk")


@case("client-under-wrong-company")
def _():
    code, errors, warnings, _ = run(clients=CL_EX, lines=[hdr("IN.ABC")])
    assert code == 1
    assert_why(errors, "why=icx.cl.unk")


@case("bare-client-without-registry-warns")
def _():
    code, errors, warnings, _ = run(lines=[hdr("ABC")])
    assert_ok(code, errors)
    assert warnings, "expected a warning without registry"
    assert any("why=icx.cl.warn" in w for w in warnings), warnings


@case("unknown-company-without-registry")
def _():
    code, errors, warnings, _ = run(lines=[hdr("ZZ.ABC")])
    assert code == 1
    assert_why(errors, "why=icx.co.unk")


@case("shorthand-without-registry-warns")
def _():
    code, errors, warnings, stats = run(lines=[hdr("CM.ABC")])
    assert_ok(code, errors)
    assert any("why=icx.cl.warn" in w for w in warnings), warnings
    p = stats["parsed"][0]
    assert p["company_full"] == "C-TBD-XXXX", p
    assert p["client_id"] is None, p


# --- outbound tokens ---

@case("outbound-complete-ok")
def _():
    line = hdr("CM.ABC", extra=out_tok())
    code, errors, warnings, _ = run(clients=CL_EX, lines=[line], outbound=True)
    assert_ok(code, errors)


@case("outbound-missing-tokens")
def _():
    code, errors, warnings, _ = run(
        clients=CL_EX, lines=[hdr("CM.ABC")], outbound=True,
    )
    assert code == 1
    assert_why(errors, "why=icx.ext.tok")


@case("outbound-missing-each-key")
def _():
    full = {
        "co": "cogent-marketing",
        "cl": "abc",
        "topic": "voice-intake-config",
        "icx": "1.2.0",
    }
    for drop in ("co", "cl", "topic", "icx"):
        kv = " ".join("%s=%s" % (k, v) for k, v in full.items() if k != drop)
        code, errors, warnings, _ = run(
            clients=CL_EX, lines=[hdr("CM.ABC", extra=kv)], outbound=True,
        )
        assert code == 1, drop
        assert_why(errors, "why=icx.ext.tok")


@case("internal-line-no-outbound-flag-ok")
def _():
    code, errors, warnings, _ = run(clients=CL_EX, lines=[hdr("CM.ABC")])
    assert_ok(code, errors)


@case("unknown-object-still-icx-unk")
def _():
    code, errors, warnings, _ = run(
        clients=CL_EX, lines=[hdr("CM.ABC", obj="no.such.code")],
    )
    assert code == 1
    assert_why(errors, "why=icx.unk")


@case("x-word-unknown-concept-ok")
def _():
    code, errors, warnings, _ = run(
        clients=CL_EX, lines=[hdr("IN.INT0", verb="FYI", obj="x.widget")],
    )
    assert_ok(code, errors)


# --- registry loading ---

@case("example-registry-loads")
def _():
    by_short, errors = V.load_clients(CL_EX)
    assert not errors, errors
    assert "ABC" in by_short
    assert by_short["ABC"]["company"] == "CM"
    assert by_short["ABC"]["id"] == "0000"
    assert by_short["ABC"]["name"] == "Example Client"
    assert "XYZ" in by_short and by_short["XYZ"]["id"] == "0001"


@case("private-ein4-overlay")
def _():
    customers, ein, errors = V.load_private_registry(CL_EX)
    assert not errors, errors
    assert ein["IN"] == "0000"
    parsed, e, w = V.resolve_client_slot(
        "IN.INT0", book(), customers, ein_overlay=ein,
    )
    assert not e, e
    assert parsed["company_full"] == "I-MD-0000", parsed


@case("clients-flag-and-env")
def _():
    args = V.parse_args([CB, IDX, "--clients", CL_EX, "--outbound"])
    assert args.clients == CL_EX
    assert args.outbound is True
    old = os.environ.get("ICX_CLIENTS")
    os.environ["ICX_CLIENTS"] = CL_EX
    try:
        args = V.parse_args([CB, IDX])
        assert args.clients == CL_EX
    finally:
        if old is None:
            os.environ.pop("ICX_CLIENTS", None)
        else:
            os.environ["ICX_CLIENTS"] = old


@case("list-shaped-registry")
def _():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(
            "clients:\n"
            "  - {id: '0000', short: ABC, company: CM, name: Example Client}\n"
        )
        path = f.name
    try:
        by_short, errors = V.load_clients(path)
        assert not errors, errors
        assert by_short["ABC"]["company"] == "CM"
        code, err, _, _ = run(clients=path, lines=[hdr("ABC")])
        assert_ok(code, err)
    finally:
        os.remove(path)


@case("default-company-cm-when-omitted")
def _():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write("clients:\n  - {id: '0000', short: ABC, name: Example Client}\n")
        path = f.name
    try:
        customers, ein, errors = V.load_private_registry(path)
        assert not errors, errors
        parsed, e, w = V.resolve_client_slot("ABC", book(), customers)
        assert not e, e
        assert parsed["company_short"] == "CM", parsed
        assert parsed["company_full"] == "C-TBD-XXXX", parsed
        assert parsed["client_id"] == "0000", parsed
    finally:
        os.remove(path)


@case("duplicate-customer-shorthand-rejected")
def _():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(
            "clients:\n"
            "  - {id: '0000', short: ABC, company: CM, name: Example Client}\n"
            "  - {id: '0002', short: ABC, company: CM, name: Other}\n"
        )
        path = f.name
    try:
        _cust, _ein, errors = V.load_private_registry(path)
        assert any("duplicate client shorthand" in e for e in errors), errors
    finally:
        os.remove(path)


@case("duplicate-customer-id-rejected")
def _():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(
            "clients:\n"
            "  - {id: '0000', short: ABC, company: CM, name: Example Client}\n"
            "  - {id: '0000', short: XYZ, company: CM, name: Other}\n"
        )
        path = f.name
    try:
        _cust, _ein, errors = V.load_private_registry(path)
        assert any("duplicate client id" in e for e in errors), errors
    finally:
        os.remove(path)


@case("company-full-form-regex")
def _():
    assert V.CO_PROD.match("I-MD-XXXX")
    assert V.CO_PROD.match("I-MD-0000")
    assert not V.CO_PROD.match("C-TBD-XXXX")
    assert V.CO_SEG.match("C-TBD-XXXX")
    assert not V.is_company_form("IN")
    assert not V.is_company_form("C")
    assert not V.is_company_form("I-MD-XXXXX")


if __name__ == "__main__":
    fails = [r for r in results if not r[1]]
    for n, g, m in results:
        print(("PASS " if g else "FAIL ") + n + ("" if g else " " + m))
    print("TOTAL %d PASS %d FAIL %d" % (len(results), len(results) - len(fails), len(fails)))
    sys.exit(1 if fails else 0)
