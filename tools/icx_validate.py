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
# Production company full code: <letter>-<2-letter state>-<EIN last four or XXXX>.
# TBD is the pending-state token until a 2-letter state is assigned.
CO_PROD = re.compile(r"^[A-Z]-[A-Z]{2}-(\d{4}|XXXX)$")
CO_SEG = re.compile(r"^[A-Z]-(?:[A-Z]{2}|TBD)-(\d{4}|XXXX)$")
CO_SHORT = re.compile(r"^[A-Z]{2}$")
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


def is_company_form(code):
    """True if code matches the Rule 14a full company form (or pending TBD)."""
    return bool(code) and bool(CO_SEG.match(code))


def apply_ein4(full, ein4):
    """Replace the XXXX (or pending) tail of a full code with four digits."""
    if not full or not ein4:
        return full
    letter, state, _tail = full.split("-", 2)
    return "%s-%s-%s" % (letter, state, ein4)


def empty_companies():
    return {"by_short": {}, "by_full": {}, "records": []}


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
    """Build the public company book: shorthand -> full code.

    Full codes may repeat (CM and CD both map to C-TBD-XXXX). Shorthand
    is unique. The first letter of a full code is never treated as unique.
    """
    book = empty_companies()
    for c in cb.get("companies", []):
        short = c.get("short")
        full = c.get("full") or c.get("code")
        name = c.get("name")
        if not short or not full or not name:
            errors.append(f"company missing short, full, or name: {c}")
            continue
        if not CO_SHORT.match(short):
            errors.append(f"bad company shorthand '{short}' (two A-Z letters)")
        if not is_company_form(full):
            errors.append(
                f"bad company full '{full}' "
                f"(L-ST-#### / L-ST-XXXX, or L-TBD-XXXX while pending)"
            )
        if short in book["by_short"]:
            errors.append(f"duplicate company shorthand: {short}")
        rec = dict(c)
        rec["short"] = short
        rec["full"] = full
        book["by_short"][short] = rec
        book["by_full"].setdefault(full, []).append(short)
        book["records"].append(rec)
    return book


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


def load_private_registry(path):
    """Load the private customer + EIN overlay registry.

    customers:
      - {id: 0000, short: ABC, company: CM, name: Example Client}
    companies:
      IN: {ein4: "0000"}   # fake last-four overlay for I-MD-XXXX

    Rejects duplicate customer ids and duplicate customer shorthand.
    """
    data = load_yaml(path) or {}
    errors = []
    customers = {"by_short": {}, "by_id": {}}
    ein_overlay = {}

    raw_co = data.get("companies")
    if isinstance(raw_co, dict):
        for key, meta in raw_co.items():
            if not isinstance(meta, dict):
                errors.append(f"private company '{key}' must map to a mapping")
                continue
            ein4 = meta.get("ein4")
            if ein4 is None:
                continue
            ein4 = str(ein4).strip()
            if not re.fullmatch(r"\d{4}", ein4):
                errors.append(f"bad ein4 for '{key}' (four digits, fake in examples)")
                continue
            ein_overlay[str(key)] = ein4
    elif raw_co is not None:
        errors.append("private companies must be a mapping of shorthand or full code")

    raw = data.get("clients")
    if raw is None:
        return customers, ein_overlay, errors

    items = []
    if isinstance(raw, dict):
        for key, meta in raw.items():
            if meta is None:
                meta = {}
            if not isinstance(meta, dict):
                errors.append(f"client '{key}' must map to a mapping")
                continue
            rec = dict(meta)
            rec.setdefault("short", str(key))
            items.append(rec)
    elif isinstance(raw, list):
        for meta in raw:
            if not isinstance(meta, dict):
                errors.append(f"client entry must be a mapping: {meta}")
                continue
            items.append(dict(meta))
    else:
        errors.append("clients registry must be a mapping or a list")
        return customers, ein_overlay, errors

    for rec in items:
        short = rec.get("short") or rec.get("code")
        cid = rec.get("id")
        company = rec.get("company", DEFAULT_CLIENT_COMPANY)
        name = rec.get("name")
        if short is None or cid is None:
            errors.append(f"client missing id or short: {rec}")
            continue
        short = str(short)
        cid_s = str(cid).strip()
        if not re.fullmatch(r"\d+", cid_s):
            errors.append(f"client id '{cid}' must be numeric")
            continue
        if not CL_SEG.match(short):
            errors.append(f"bad client shorthand '{short}' (upper, <=6 chars)")
        if not CO_SHORT.match(str(company)) and not is_company_form(str(company)):
            errors.append(f"bad client company '{company}'")
        id_key = str(int(cid_s))
        if short in customers["by_short"]:
            errors.append(f"duplicate client shorthand: {short} why=icx.cl.unk")
        if id_key in customers["by_id"]:
            errors.append(f"duplicate client id: {cid_s} why=icx.cl.unk")
        entry = {
            "id": cid_s,
            "short": short,
            "company": str(company),
            "name": name,
        }
        customers["by_short"][short] = entry
        customers["by_id"][id_key] = entry
    return customers, ein_overlay, errors


def load_clients(path):
    """Back-compat wrapper: short -> record, including company."""
    customers, _ein, errors = load_private_registry(path)
    return customers["by_short"], errors


def full_for_short(short, book, ein_overlay=None):
    rec = book["by_short"].get(short)
    if not rec:
        return None
    full = rec["full"]
    overlay = ein_overlay or {}
    if short in overlay:
        return apply_ein4(full, overlay[short])
    if full in overlay:
        return apply_ein4(full, overlay[full])
    return full


def resolve_company(token, book, ein_overlay=None):
    """Map a company token to (short, full) or errors.

    Accepts registered shorthand (IN, CM, CD) or a registered full code.
    A single letter is never unique (C is shared by both Cogent entities).
    """
    errors = []
    if not token:
        errors.append("empty company why=icx.co.unk")
        return None, None, errors
    if token in book["by_short"]:
        return token, full_for_short(token, book, ein_overlay), errors
    if token in book["by_full"]:
        shorts = book["by_full"][token]
        short = shorts[0] if len(shorts) == 1 else None
        full = token
        overlay = ein_overlay or {}
        if short and short in overlay:
            full = apply_ein4(full, overlay[short])
        elif token in overlay:
            full = apply_ein4(full, overlay[token])
        return short, full, errors
    # Private EIN overlay: I-MD-0000 resolves back to I-MD-XXXX / IN.
    overlay = ein_overlay or {}
    for short, ein4 in overlay.items():
        public_full = None
        if short in book["by_short"]:
            public_full = book["by_short"][short]["full"]
        elif short in book["by_full"]:
            public_full = short
        if not public_full:
            continue
        if apply_ein4(public_full, ein4) == token:
            resolved_short = short if short in book["by_short"] else (
                book["by_full"][public_full][0]
                if public_full in book["by_full"]
                and len(book["by_full"][public_full]) == 1
                else None
            )
            return resolved_short, token, errors
    errors.append(f"unknown company '{token}' why=icx.co.unk")
    return None, None, errors


def make_parsed(slot, company_short, company_full, client_short, client_id=None):
    resolved_client = client_id if client_id is not None else client_short
    if company_full and resolved_client:
        resolved = "%s.%s" % (company_full, resolved_client)
    else:
        resolved = company_full or slot
    return {
        "input": slot,
        "company_short": company_short,
        "company_full": company_full,
        "client_short": client_short,
        "client_id": client_id,
        "resolved": resolved,
    }


def resolve_client_slot(slot, companies, registry, ein_overlay=None):
    """Resolve a CLIENT/LANE slot.

    Headers use shorthand (IN.INT0, CM.ABC). Full codes are also accepted.
    Parsed output expands company shorthand to full code, and (when a
    registry is loaded) customer shorthand to numeric id.

    Returns (parsed, errors, warnings).
    """
    errors, warnings = [], []
    if not slot:
        errors.append("empty client slot why=icx.cl.unk")
        return None, errors, warnings

    # Company book may be the new dict or a plain short->rec mapping used in tests.
    if isinstance(companies, dict) and "by_short" in companies:
        book = companies
    else:
        book = empty_companies()
        for k, rec in (companies or {}).items():
            rec = dict(rec) if isinstance(rec, dict) else {}
            rec.setdefault("short", k)
            rec.setdefault("full", rec.get("code") or k)
            book["by_short"][k] = rec
            book["by_full"].setdefault(rec["full"], []).append(k)
            book["records"].append(rec)

    customers = None
    if registry is None:
        customers = None
    elif isinstance(registry, dict) and "by_short" in registry:
        customers = registry
    else:
        customers = {"by_short": registry or {}, "by_id": {}}

    def lookup_customer(token):
        if customers is None:
            return None
        return customers["by_short"].get(token)

    if "." in slot:
        company, client, *extra = slot.split(".")
        if extra:
            errors.append(f"bad client slot '{slot}' why=icx.cl.unk")
            return None, errors, warnings
        c_short, c_full, c_err = resolve_company(company, book, ein_overlay)
        errors.extend(c_err)
        if c_err:
            return None, errors, warnings
        if client == INTERNAL_CLIENT:
            return (
                make_parsed(slot, c_short, c_full, INTERNAL_CLIENT, None),
                errors, warnings,
            )
        if customers is None:
            if not CL_SEG.match(client):
                errors.append(f"bad client code '{client}' why=icx.cl.unk")
                return None, errors, warnings
            warnings.append(
                f"client '{client}' not checked (no registry) why=icx.cl.warn"
            )
            return (
                make_parsed(slot, c_short, c_full, client, None),
                errors, warnings,
            )
        rec = lookup_customer(client)
        if rec is None:
            errors.append(f"unknown client '{client}' why=icx.cl.unk")
            return None, errors, warnings
        parent = rec.get("company", DEFAULT_CLIENT_COMPANY)
        p_short, p_full, p_err = resolve_company(parent, book, ein_overlay)
        if p_err:
            errors.extend(p_err)
            return None, errors, warnings
        if c_short and p_short and c_short != p_short:
            errors.append(
                f"client '{client}' is not under '{company}' why=icx.cl.unk"
            )
            return None, errors, warnings
        if not c_short and c_full and p_full and c_full != p_full:
            errors.append(
                f"client '{client}' is not under '{company}' why=icx.cl.unk"
            )
            return None, errors, warnings
        return (
            make_parsed(slot, p_short or c_short, c_full or p_full,
                        rec["short"], rec["id"]),
            errors, warnings,
        )

    # Bare token: company shorthand/full, INT0, or a customer shorthand.
    if slot == INTERNAL_CLIENT:
        d_short, d_full, d_err = resolve_company("IN", book, ein_overlay)
        errors.extend(d_err)
        return (
            make_parsed(slot, d_short or "IN", d_full or "I-MD-XXXX",
                        INTERNAL_CLIENT, None),
            errors, warnings,
        )
    c_short, c_full, c_err = resolve_company(slot, book, ein_overlay)
    if not c_err:
        return make_parsed(slot, c_short, c_full, None, None), errors, warnings
    # A single letter is never a unique company (C is shared by both Cogent
    # entities). Two-letter tokens that are not registered shorthand are
    # unknown companies, not customers.
    if len(slot) == 1 or (CO_SHORT.match(slot) and slot not in book["by_short"]):
        errors.append(f"unknown company '{slot}' why=icx.co.unk")
        return None, errors, warnings
    if customers is None:
        if not CL_SEG.match(slot):
            errors.append(f"unknown company '{slot}' why=icx.co.unk")
            return None, errors, warnings
        warnings.append(
            f"client '{slot}' not checked (no registry) why=icx.cl.warn"
        )
        p_short, p_full, p_err = resolve_company(
            DEFAULT_CLIENT_COMPANY, book, ein_overlay,
        )
        errors.extend(p_err)
        return (
            make_parsed(slot, p_short, p_full, slot, None),
            errors, warnings,
        )
    rec = lookup_customer(slot)
    if rec is None:
        errors.append(f"unknown client '{slot}' why=icx.cl.unk")
        return None, errors, warnings
    p_short, p_full, p_err = resolve_company(
        rec.get("company", DEFAULT_CLIENT_COMPANY), book, ein_overlay,
    )
    errors.extend(p_err)
    if p_err:
        return None, errors, warnings
    return (
        make_parsed(slot, p_short, p_full, rec["short"], rec["id"]),
        errors, warnings,
    )


def check_object_token(obj, codes, facets, errors):
    if not obj:
        errors.append("missing object why=icx.unk")
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


def validate_line(line, companies, codes, facets, verb_codes, registry,
                  outbound=False, ein_overlay=None):
    """Validate one ICOM header. Returns (errors, warnings, parsed)."""
    errors, warnings = [], []
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return errors, warnings, None
    m = LINE_RE.match(raw)
    if not m:
        errors.append(f"bad ICOM header: {raw}")
        return errors, warnings, None

    slot = m.group("client")
    parsed, slot_err, slot_warn = resolve_client_slot(
        slot, companies, registry, ein_overlay=ein_overlay,
    )
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
    return errors, warnings, parsed


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
    ein_overlay = None
    if clients_path:
        customers, ein_overlay, reg_err = load_private_registry(clients_path)
        errors.extend(reg_err)
        registry = customers
        for short, rec in customers["by_short"].items():
            parent = rec.get("company", DEFAULT_CLIENT_COMPANY)
            p_short, _p_full, p_err = resolve_company(
                parent, companies, ein_overlay,
            )
            if p_err:
                errors.append(
                    f"client '{short}' unknown company '{parent}' why=icx.co.unk"
                )
            rec["_company_short"] = p_short

    parsed_lines = []
    line_count = 0
    for line in lines or []:
        if not line.strip() or line.strip().startswith("#"):
            continue
        line_count += 1
        e, w, parsed = validate_line(
            line, companies, codes, facets, verb_codes, registry,
            outbound=outbound, ein_overlay=ein_overlay,
        )
        prefix = (line.strip()[:48] + "...") if len(line.strip()) > 48 else line.strip()
        for item in e:
            errors.append(f"{item} [{prefix}]")
        for item in w:
            warnings.append(f"{item} [{prefix}]")
        if parsed:
            parsed_lines.append(parsed)

    stats = {
        "codes": len(codes),
        "verbs": len(verbs),
        "facets": len(facets),
        "tomb": len(tomb),
        "index": len(idx),
        "companies": len(companies["records"]),
        "clients": 0 if registry is None else len(registry["by_short"]),
        "lines": line_count,
        "parsed": parsed_lines,
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


def format_parsed(parsed):
    if not parsed:
        return None
    parts = ["parsed %s" % parsed["resolved"]]
    if parsed.get("company_short"):
        parts.append("co_short=%s" % parsed["company_short"])
    if parsed.get("company_full"):
        parts.append("co_full=%s" % parsed["company_full"])
    if parsed.get("client_short"):
        parts.append("cl_short=%s" % parsed["client_short"])
    if parsed.get("client_id") is not None:
        parts.append("cl_id=%s" % parsed["client_id"])
    return " ".join(parts)


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
    for parsed in stats.get("parsed") or []:
        line = format_parsed(parsed)
        if line:
            print(line)
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
