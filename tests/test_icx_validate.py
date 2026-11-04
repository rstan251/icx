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


@case("companies-in-codebook")
def _():
    cb = V.load_yaml(CB)["icx"]
    assert cb["version"] == "1.2.0"
    got = {c["code"]: c["name"] for c in cb["companies"]}
    assert got == {
        "IN": "Iron Noodle LLC",
        "CM": "Cogent Marketing LLC",
        "CD": "Cogent Digital LLC",
    }


# --- Rule 14a client slot ---

@case("company-dot-client-ok")
def _():
    code, errors, warnings, _ = run(clients=CL_EX, lines=[hdr("CM.ABC")])
    assert_ok(code, errors)


@case("bare-registered-client-ok")
def _():
    code, errors, warnings, _ = run(clients=CL_EX, lines=[hdr("ABC")])
    assert_ok(code, errors)
    resolved, e, w = V.resolve_client_slot("ABC", {"IN": {}, "CM": {}, "CD": {}},
                                           V.load_clients(CL_EX)[0])
    assert resolved == "CM.ABC", resolved
    assert not e


@case("bare-xyz-ok")
def _():
    code, errors, warnings, _ = run(clients=CL_EX, lines=[hdr("XYZ")])
    assert_ok(code, errors)


@case("int0-under-any-company")
def _():
    for slot in ("IN.INT0", "CM.INT0", "CD.INT0", "INT0"):
        code, errors, warnings, _ = run(clients=CL_EX, lines=[hdr(slot, verb="GO", obj="org.proto")])
        assert_ok(code, errors)


@case("int0-default-is-in-int0")
def _():
    resolved, e, w = V.resolve_client_slot(
        "INT0", {"IN": {}, "CM": {}, "CD": {}}, None,
    )
    assert resolved == "IN.INT0", resolved
    assert not e


@case("company-prefix-matches-all-clients")
def _():
    code, errors, warnings, _ = run(clients=CL_EX, lines=[hdr("CM")])
    assert_ok(code, errors)


@case("unknown-company-prefix")
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


@case("company-dot-client-without-registry-warns")
def _():
    code, errors, warnings, _ = run(lines=[hdr("CM.ABC")])
    assert_ok(code, errors)
    assert any("why=icx.cl.warn" in w for w in warnings), warnings


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
    reg, errors = V.load_clients(CL_EX)
    assert not errors, errors
    assert "ABC" in reg and reg["ABC"]["company"] == "CM"
    assert "XYZ" in reg and reg["XYZ"]["company"] == "CM"


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
        f.write("clients:\n  - {code: ABC, company: CM}\n")
        path = f.name
    try:
        reg, errors = V.load_clients(path)
        assert not errors, errors
        assert reg["ABC"]["company"] == "CM"
        code, err, _, _ = run(clients=path, lines=[hdr("ABC")])
        assert_ok(code, err)
    finally:
        os.remove(path)


@case("default-company-cm-when-omitted")
def _():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write("clients:\n  ABC: {}\n")
        path = f.name
    try:
        resolved, e, w = V.resolve_client_slot(
            "ABC", {"IN": {}, "CM": {}, "CD": {}}, V.load_clients(path)[0],
        )
        assert resolved == "CM.ABC", resolved
        assert not e
    finally:
        os.remove(path)


if __name__ == "__main__":
    fails = [r for r in results if not r[1]]
    for n, g, m in results:
        print(("PASS " if g else "FAIL ") + n + ("" if g else " " + m))
    print("TOTAL %d PASS %d FAIL %d" % (len(results), len(results) - len(fails), len(fails)))
    sys.exit(1 if fails else 0)
