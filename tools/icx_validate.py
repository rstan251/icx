#!/usr/bin/env python3
"""Validate an ICX codebook and its relative index.

Checks class/code segments, optional work-state verbs, facets, tombstones, and index targets.

Usage: icx_validate.py CODEBOOK.yaml INDEX.yaml
Exit 0 when valid, 1 with one line per error otherwise.
"""
import re
import sys

import yaml

SEG = re.compile(r"^[a-z][a-z0-9]{0,5}$")
MAX_DEPTH = 4


def split(code):
    base, _, facet = code.partition("~")
    return base, facet


def main(codebook_path, index_path):
    cb = yaml.safe_load(open(codebook_path))["icx"]
    idx = yaml.safe_load(open(index_path))["index"]
    errors = []

    codes = {}
    for c in cb["classes"]:
        codes[c["code"]] = c
    for c in cb.get("codes", []):
        if c["code"] in codes:
            errors.append(f"duplicate code: {c['code']}")
        codes[c["code"]] = c
    verbs = cb.get("verbs", [])
    verb_codes = set()
    for v in verbs:
        if not v.get("code") or not v.get("name"):
            errors.append(f"verb missing code or name: {v}")
            continue
        if v["code"] in verb_codes:
            errors.append(f"duplicate verb: {v['code']}")
        verb_codes.add(v["code"])
    facets = {f["code"] for f in cb.get("facets", [])}
    tomb = {t["old"]: t["new"] for t in cb.get("tombstones", [])}

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

    for old, new in tomb.items():
        if split(new)[0] not in codes:
            errors.append(f"tombstone {old} -> unknown {new}")

    for f in facets:
        head = f.split(".")[0]
        if not SEG.match(head):
            errors.append(f"bad facet: {f}")

    for term, target in idx.items():
        base, facet = split(target)
        if base not in codes:
            errors.append(f"index '{term}' -> unknown code {base}")
        if facet and facet not in facets and facet.split(".")[0] + ".*" not in facets:
            errors.append(f"index '{term}' -> unknown facet ~{facet}")

    for e in errors:
        print(e)
    print(f"{'FAIL' if errors else 'OK'}: {len(codes)} codes, {len(verbs)} verbs, "
          f"{len(facets)} facets, {len(tomb)} tombstones, {len(idx)} index terms")
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
