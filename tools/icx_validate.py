#!/usr/bin/env python3
"""Validate an ICX codebook, its relative index, and optional ICOM lines.

Checks class/code segments, optional work-state verbs, facets, tombstones,
index targets, company codes (Rule 14a), and (when given) the CLIENT slot
and outbound tokens.

Usage:
  icx_validate.py CODEBOOK.yaml INDEX.yaml
  icx_validate.py CODEBOOK.yaml INDEX.yaml [--clients PATH] [--outbound]
                   [--line 'ICOM line'] [--lines FILE]

Exit 0 when valid, 1 with one line per error otherwise.
Warnings (no registry for a bare client code) print as WARN and do not fail.

Environment:
  ICX_CLIENTS  path to a private client registry (same as --clients)
"""
import argparse
import os
import re
import sys

import yaml

SEG = re.compile(r"^[a-z][a-z0-9]{0,5}$")
CO_SEG = re.compile(r"^[A-Z][A-Z0-9]{0,5}$")
CL_SEG = re.compile(r"^[A-Z][A-Z0-9]{0,5}$")
WORD_TOK = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_DEPTH = 4
DEFAULT_CLIENT_COMPANY = "CM"
DEFAULT_INTERNAL = "IN.INT0"
INTERNAL_CLIENT = "INT0"
OUTBOUND_KEYS = ("co", "cl", "topic", "icx")

# @FROM>ICOM>TO[,TO] P0-3 CLIENT #ticket VERB ...
LINE_RE = re.compile(
    r"^@(?P<frm>\S+)>ICOM>(?P<to>\S+)"
    r"\s+(?P<pri>P[0-3])"
    r"\s+(?P<client>\S+)"
    r"\s+(?P<ticket>#\S+)"
    r"\s+(?P<verb>\S+)"
    r"(?:\s+(?P<rest>.*))?$"
)


def split(code):
    base, _, facet = code.partition("~")
    return base, facet


def kv_tokens(rest):
    """Return key=val tokens from the trailer of an ICOM line."""
    out = {}
    if not rest:
        return out
    for tok in rest.split():
        if "=" not in tok:
            continue
        k, _, v = tok.partition("=")
        out[k] = v
    return out


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def load_clients(path):
    """Load a private client registry.

    Accepted shapes:
      clients:
        ABC: {company: CM}
      clients:
        - {code: ABC, company: CM}
    Missing company defaults to CM. INT0 is always valid and need not appear.
    """
    data = load_yaml(path) or {}
    raw = data.get("clients", data)
    registry = {}
    errors = []
    if raw is None:
        return registry, errors
    if isinstance(raw, dict):
        items = []
        for code, meta in raw.items():
            if meta is None:
                meta = {}
            if not isinstance(meta, dict):
                errors.append(f"client '{code}' must map to a mapping")
                continue
            items.append((str(code), meta))
    elif isinstance(raw, list):
        items = []
        for meta in raw:
            if not isinstance(meta, dict) or not meta.get("code"):
                errors.append(f"client entry missing code: {meta}")
                continue
            items.append((str(meta["code"]), meta))
    else:
        errors.append("clients registry must be a mapping or a list")
        return registry, errors

    for code, meta in items:
        if not CL_SEG.match(code):
            errors.append(f"bad client code '{code}' (upper, <=6 chars)")
        company = meta.get("company", DEFAULT_CLIENT_COMPANY)
        if code in registry:
            errors.append(f"duplicate client: {code}")
        registry[code] = {"company": company, **meta}
    return registry, errors


def collect_codes(cb, errors):
    codes = {}
    for c in cb["classes"]:
        codes[c["code"]] = c
    for c in cb.get("codes", []):
        if c["code"] in codes:
            errors.append(f"duplicate code: {c['code']}")
        codes[c["code"]] = c
    return codes


def collect_verbs(cb, errors):
    verbs = cb.get("verbs", [])
    verb_codes = set()
    for v in verbs:
        if not v.get("code") or not v.get("name"):
            errors.append(f"verb missing code or name: {v}")
            continue
        if v["code"] in verb_codes:
            errors.append(f"duplicate verb: {v['code']}")
        verb_codes.add(v["code"])
    return verbs, verb_codes


def collect_companies(cb, errors):
    companies = {}
    for c in cb.get("companies", []):
        code = c.get("code")
        name = c.get("name")
        if not code or not name:
            errors.append(f"company missing code or name: {c}")
            continue
        if not CO_SEG.match(code):
            errors.append(f"bad company '{code}' (upper, <=6 chars)")
        if code in companies:
            errors.append(f"duplicate company: {code}")
        companies[code] = c
    return companies


def check_codes(codes, tomb, errors):
    for code in codes:
        segs = code.split(".")
        if len(segs) > MAX_DEPTH:
            errors.append(f"too deep (>{MAX_DEPTH}): {code}")
        for s in segs:
            if not SEG.match(s):
                errors.append(f"bad segment '{s}' in {code} (lower, <=6 chars)")
        for i in range(1, len(segs)):
            parent = ".".join(segs[:i])
            if parent not in codes:
                errors.append(f"missing parent {parent} for {code}")
        if code in tomb:
            errors.append(f"live code is also tombstoned: {code}")


def check_tombstones(tomb, codes, errors):
    for old, new in tomb.items():
        if split(new)[0] not in codes:
            errors.append(f"tombstone {old} -> unknown {new}")


def check_facets(facets, errors):
    for f in facets:
        head = f.split(".")[0]
        if not SEG.match(head):
            errors.append(f"bad facet: {f}")


def check_index(idx, codes, facets, errors):
    for term, target in idx.items():
        base, facet = split(target)
        if base not in codes:
            errors.append(f"index '{term}' -> unknown code {base}")
        if facet and facet not in facets and facet.split(".")[0] + ".*" not in facets:
            errors.append(f"index '{term}' -> unknown facet ~{facet}")


def resolve_client_slot(slot, companies, registry):
    """Resolve a CLIENT/LANE slot.

    Returns (resolved, errors, warnings). resolved is COMPANY.CLIENT or a
    bare registered company code (prefix match for all that company's traffic).
    """
    errors, warnings = [], []
    if not slot:
        errors.append(f"empty client slot why=icx.cl.unk")
        return None, errors, warnings

    if "." in slot:
        company, client, *extra = slot.split(".")
        if extra:
            errors.append(f"bad client slot '{slot}' why=icx.cl.unk")
            return None, errors, warnings
        if company not in companies:
            errors.append(f"unknown company '{company}' why=icx.co.unk")
            return None, errors, warnings
        if client == INTERNAL_CLIENT:
            return f"{company}.{INTERNAL_CLIENT}", errors, warnings
        if registry is None:
            if not CL_SEG.match(client):
                errors.append(f"bad client code '{client}' why=icx.cl.unk")
                return None, errors, warnings
            warnings.append(
                f"client '{client}' not checked (no registry) why=icx.cl.warn"
            )
            return f"{company}.{client}", errors, warnings
        if client not in registry:
            errors.append(f"unknown client '{client}' why=icx.cl.unk")
            return None, errors, warnings
        parent = registry[client].get("company", DEFAULT_CLIENT_COMPANY)
        if parent != company:
            errors.append(
                f"client '{client}' is not under '{company}' why=icx.cl.unk"
            )
            return None, errors, warnings
        return f"{company}.{client}", errors, warnings

    # Bare token: company prefix, INT0, or a client code.
    if slot in companies:
        return slot, errors, warnings
    if slot == INTERNAL_CLIENT:
        return DEFAULT_INTERNAL, errors, warnings
    if registry is None:
        if not CL_SEG.match(slot):
            errors.append(f"bad client code '{slot}' why=icx.cl.unk")
            return None, errors, warnings
        warnings.append(
            f"client '{slot}' not checked (no registry) why=icx.cl.warn"
        )
        return f"{DEFAULT_CLIENT_COMPANY}.{slot}", errors, warnings
    if slot not in registry:
        errors.append(f"unknown client '{slot}' why=icx.cl.unk")
        return None, errors, warnings
    parent = registry[slot].get("company", DEFAULT_CLIENT_COMPANY)
    if parent not in companies:
        errors.append(f"unknown company '{parent}' why=icx.co.unk")
        return None, errors, warnings
    return f"{parent}.{slot}", errors, warnings


def check_object_token(obj, codes, facets, errors):
    if not obj:
        errors.append(f"missing object why=icx.unk")
        return
    base, facet = split(obj)
    segs = base.split(".")
    if segs and segs[0] == "x":
        for s in segs:
            if not SEG.match(s):
                errors.append(f"bad segment '{s}' in {obj} why=icx.unk")
        if facet and facet not in facets and facet.split(".")[0] + ".*" not in facets:
            errors.append(f"unknown facet ~{facet} why=icx.unk")
        return
    if base not in codes:
        errors.append(f"unknown object {obj} why=icx.unk")
        return
    if facet and facet not in facets and facet.split(".")[0] + ".*" not in facets:
        errors.append(f"unknown facet ~{facet} why=icx.unk")


def validate_line(line, companies, codes, facets, verb_codes, registry, outbound=False):
    """Validate one ICOM header. Returns (errors, warnings)."""
    errors, warnings = [], []
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return errors, warnings
    m = LINE_RE.match(raw)
    if not m:
        errors.append(f"bad ICOM header: {raw}")
        return errors, warnings

    slot = m.group("client")
    _, slot_err, slot_warn = resolve_client_slot(slot, companies, registry)
    errors.extend(slot_err)
    warnings.extend(slot_warn)

    rest = m.group("rest") or ""
    tokens = rest.split()
    obj = None
    for tok in tokens:
        if "=" in tok:
            break
        if verb_codes and tok in verb_codes:
            continue
        obj = tok
        break
    if obj is None and tokens and "=" not in tokens[0]:
        obj = tokens[0]
    check_object_token(obj, codes, facets, errors)

    if outbound:
        kv = kv_tokens(rest)
        missing = [k for k in OUTBOUND_KEYS if not kv.get(k)]
        if missing:
            errors.append(
                f"outbound missing {','.join(missing)}= why=icx.ext.tok"
            )
        else:
            for k in ("co", "cl", "topic"):
                if not WORD_TOK.match(kv[k]):
                    errors.append(
                        f"outbound {k}={kv[k]} must be lowercase-hyphenated "
                        f"why=icx.ext.tok"
                    )
    return errors, warnings


def read_lines(paths, extra):
    out = list(extra or [])
    for path in paths or []:
        with open(path) as f:
            out.extend(f.readlines())
    return out


def validate(codebook_path, index_path, clients_path=None, lines=None,
             outbound=False):
    """Run all checks. Returns (exit_code, errors, warnings, stats)."""
    errors = []
    warnings = []
    cb = load_yaml(codebook_path)["icx"]
    idx = load_yaml(index_path)["index"]

    codes = collect_codes(cb, errors)
    verbs, verb_codes = collect_verbs(cb, errors)
    companies = collect_companies(cb, errors)
    facets = {f["code"] for f in cb.get("facets", [])}
    tomb = {t["old"]: t["new"] for t in cb.get("tombstones", [])}

    check_codes(codes, tomb, errors)
    check_tombstones(tomb, codes, errors)
    check_facets(facets, errors)
    check_index(idx, codes, facets, errors)

    registry = None
    if clients_path:
        registry, reg_err = load_clients(clients_path)
        errors.extend(reg_err)
        for code, meta in registry.items():
            parent = meta.get("company", DEFAULT_CLIENT_COMPANY)
            if parent not in companies:
                errors.append(
                    f"client '{code}' unknown company '{parent}' why=icx.co.unk"
                )

    line_count = 0
    for line in lines or []:
        if not line.strip() or line.strip().startswith("#"):
            continue
        line_count += 1
        e, w = validate_line(
            line, companies, codes, facets, verb_codes, registry,
            outbound=outbound,
        )
        prefix = (line.strip()[:48] + "...") if len(line.strip()) > 48 else line.strip()
        for item in e:
            errors.append(f"{item} [{prefix}]")
        for item in w:
            warnings.append(f"{item} [{prefix}]")

    stats = {
        "codes": len(codes),
        "verbs": len(verbs),
        "facets": len(facets),
        "tomb": len(tomb),
        "index": len(idx),
        "companies": len(companies),
        "clients": 0 if registry is None else len(registry),
        "lines": line_count,
    }
    return (1 if errors else 0), errors, warnings, stats


def format_summary(errors, stats):
    extra = f", {stats['companies']} companies"
    if stats["clients"]:
        extra += f", {stats['clients']} clients"
    if stats["lines"]:
        extra += f", {stats['lines']} lines"
    return (
        f"{'FAIL' if errors else 'OK'}: {stats['codes']} codes, "
        f"{stats['verbs']} verbs, {stats['facets']} facets, "
        f"{stats['tomb']} tombstones, {stats['index']} index terms{extra}"
    )


def main(codebook_path, index_path, clients_path=None, lines=None,
         outbound=False):
    code, errors, warnings, stats = validate(
        codebook_path, index_path, clients_path=clients_path,
        lines=lines, outbound=outbound,
    )
    for w in warnings:
        print(f"WARN: {w}")
    for e in errors:
        print(e)
    print(format_summary(errors, stats))
    return code


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="icx_validate.py",
        description="Validate an ICX codebook, relative index, and optional ICOM lines.",
    )
    p.add_argument("codebook")
    p.add_argument("index")
    p.add_argument(
        "--clients",
        default=os.environ.get("ICX_CLIENTS") or None,
        help="private client registry (YAML). Also ICX_CLIENTS.",
    )
    p.add_argument(
        "--outbound",
        action="store_true",
        help="require co= cl= topic= icx= on each ICOM line (why=icx.ext.tok)",
    )
    p.add_argument(
        "--line",
        action="append",
        default=[],
        help="an ICOM header to check (repeatable)",
    )
    p.add_argument(
        "--lines",
        action="append",
        default=[],
        help="file of ICOM headers, one per line (repeatable)",
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    # Keep the original 2-arg form: icx_validate.py CODEBOOK.yaml INDEX.yaml
    args = parse_args(sys.argv[1:])
    sys.exit(main(
        args.codebook,
        args.index,
        clients_path=args.clients,
        lines=read_lines(args.lines, args.line),
        outbound=args.outbound,
    ))
