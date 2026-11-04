# ICX - Iron Concept indeX

Version: **1.2.0** · 2026-11-04

A Dewey-style concept index for messages between AI agents.

Agent fleets name the same thing many ways ("the intake line", "inbound voice", "receptionist bot"). ICX gives every concept one address. Like a library call number, the address is coarse first and narrows with each segment, so a shortened code still lands in the right section.

```
pr.voice.intake~cfg
│  │     │      └─ facet: configuration
│  │     └─ section: inbound intake
│  └─ division: voice
└─ class: client products
```

## Part of ICOM
ICX is the object vocabulary for [ICOM](https://github.com/rstan251/icom-standard), the open bot-to-bot communication standard. ICOM defines how agents talk (router, header, verbs, priorities); ICX defines what they talk about. ICOM's Rule 14 makes the header `object` slot an ICX code. Rule 14a (below) sets the `CO.CLIENT` form of the CLIENT/LANE slot.

The example codebook publishes the shared label set used with ICOM: the 10 ICX top-level classes, the 10 ICOM work-state verbs, and the three company codes. Client names and client codes are private and are not published here.

ICOM header format (Rule 11):

```
@FROM>ICOM>TO[,TO] P0-3 CO.CLIENT #ticket VERB [ACTION] object key=val ...
```

## Published label set

### Top-level object classes (10)

| Code | Class | Default owner in this example |
|---|---|---|
| `org` | fleet, agents, rules, protocol | chief-of-staff |
| `pr` | client products: voice, web, crm | product-lead |
| `sys` | infrastructure and platforms | platform |
| `ops` | process and delivery: deploy, qc, tickets | operations |
| `mk` | marketing and growth: content, outbound | marketing |
| `fin` | money: invoice, spend | operations |
| `lg` | legal and compliance | chief-of-staff |
| `rs` | research and intel: evals | engineering |
| `dt` | data and reporting: kpi, dashboards | engineering |
| `x` | unclassed; reclassify within 7 days | editor |

### ICOM work-state verbs (10)

These occupy the ICOM header verb slot. The full ICOM verb list (including FYI, ACK, NAK) is defined in the [ICOM standard](https://github.com/rstan251/icom-standard).

| Verb | Meaning |
|---|---|
| `GO` | start/approved to proceed |
| `HOLD` | pause, do not proceed |
| `BLOCKED` | cannot proceed |
| `ASK` | question needing answer |
| `REC` | recommendation |
| `DONE` | completed |
| `DO` | task assigned, execute |
| `DECIDE` | decision required from lead/owner |
| `FAIL` | review/test failed, fix needed |
| `PASS` | review/test passed |

### Company shorthand (headers and tokens)

Agents write the 2-letter shorthand in the ICOM `CO.CLIENT` slot and in tokens. The full code is the canonical record. This table is the lookup for expanding shorthand to full code. An unregistered shorthand is NAKed like an unregistered ICX code (`why=icx.co.unk`).

| Short | Full | Company | Status | Outbound `co=` |
|---|---|---|---|---|
| `IN` | `I-MD-XXXX` | Iron Noodle LLC | unverified (Maryland unconfirmed; needs owner confirmation) | `iron-noodle` |
| `CM` | `C-TBD-XXXX` | Cogent Marketing LLC | tbd (state and EIN last four pending) | `cogent-marketing` |
| `CD` | `C-TBD-XXXX` | Cogent Digital LLC | tbd (state and EIN last four pending) | `cogent-digital` |

Full-code form: `<first letter>-<2-letter state>-<last four EIN>`. Production regex: `^[A-Z]-[A-Z]{2}-(\d{4}|XXXX)$`. `TBD` is the pending-state token until a 2-letter state is assigned. The public repo ships `XXXX` only; real EIN last four live in the private registry.

Both Cogent entities share the letter `C`. They are told apart by state and EIN last four, so the validator must not treat `C` alone as unique. Prefix routing uses the shorthand (`CM` vs `CD`), not the first letter of the full code.

`INT0` is the internal / no-client lane. It is valid under any company. Default: `IN.INT0`.

Customer ids, customer shorthand, and customer names live only in the private registry. Real assignments are TBD. The repo ships fake placeholders in `clients.example.yaml` (`id: 0000`, `short: ABC`, `name: Example Client`).

## How it maps to Dewey

| Dewey Decimal | ICX |
|---|---|
| 10 main classes | 10 top classes (`org` `pr` `sys` `ops` `mk` `fin` `lg` `rs` `dt` `x`) |
| Divisions, sections, decimals | Dot segments; each one narrows its parent |
| Cutter (author) number | The message `CO.CLIENT` field. The client is never repeated inside the object. |
| Standard subdivisions (Table 1) | Facets after `~`, valid on any class |
| Geographic table (Table 2) | `~st.xx` jurisdiction facet |
| Relative index | `index.yaml`: plain-English term → code |
| Call number on the spine | The `object` field of a message header |
| Shelf order | Sort order for logs and digests |
| Weeding and relocation | Tombstones: `old → new`; codes are never reused |

## Rules

1. Segments are lower case, 1–6 characters, letters and digits, starting with a letter. Max depth 4, plus facets.
2. Every prefix of a code is itself a valid code. Shortening a code widens it; it never breaks it.
3. Account or client identity lives in its own message field (`CO.CLIENT`), never in the object code. Each part carries only what the other missed.
4. Route by prefix: the owner of the longest registered prefix receives the message unless it is addressed explicitly.
5. Exact values (IDs, amounts, dates, phone numbers, paths) are never encoded. Carry them verbatim as `key=value`.
6. Append-only. A retired code becomes a tombstone pointing to its replacement and is never reused.
7. Unknown concept: send it as `x.<word>`. The editor places it in the tree on the next review.
8. One editor (a person or a single designated agent) owns the codebook and index.

## Rule 14 (ICOM): ICX object codes

The header `object` slot holds a Dewey-style ICX concept code: class.division.section, coarse to fine, e.g. `pr.voice.intake~cfg`. Every prefix is a valid code. The lane/client stays in the `CO.CLIENT` slot, never inside the object. Exact values stay in `key=val` tokens. Unknown concept: send `x.<word>`. Unregistered codes are NAKed with `why=icx.unk`.

## Rule 14a: Company and client designation

1. The CLIENT/LANE slot is `COMPANY.CLIENT`. Agents write company shorthand in the header, e.g. `CM.ABC`, `IN.INT0`. Each public company record has `short` (2-letter, used in headers and tokens) and `full` (canonical). Lookup table: `IN` -> `I-MD-XXXX` (Iron Noodle LLC, state unverified); `CM` -> `C-TBD-XXXX` (Cogent Marketing LLC, TBD); `CD` -> `C-TBD-XXXX` (Cogent Digital LLC, TBD). The validator accepts registered shorthand or the full code, and expands shorthand to full code in parsed output. An unregistered shorthand is NAKed like an unregistered ICX code (`why=icx.co.unk`). `INT0` = internal/no client lane, valid under any company (default `IN.INT0`).
2. Backward compatible: a bare registered customer shorthand (e.g. `ABC`) stays valid. The router/validator resolves its company from the private customer registry. Default parent company is `CM` (Cogent Marketing) unless the registry says otherwise.
3. Routing and search work by prefix on the company token: `CM` matches all Cogent Marketing traffic, `CM.ABC` one customer. Do not treat `C` alone as unique (both Cogent entities share that letter; they are told apart by state and EIN last four). The ICX object code is unchanged.
4. Customer records are added to the private registry as customers are onboarded. Each record has `id` (numeric, canonical), `short` (what agents write in the client half of the slot and in tokens), `company` (company shorthand), and `name`. Real id and shorthand assignments are TBD. The registry is the lookup for expanding customer shorthand to customer ID. Unregistered customer shorthand is NAKed like an unregistered ICX code (`why=icx.cl.unk`).
5. Messages to outside agents (any ICOM line that leaves the fleet, e.g. to a partner firm's agent or a separate bot account) MUST also carry plain-word tokens `co=<company-words>` `cl=<client-words>` `topic=<topic-words>` (lowercase, hyphenated, e.g. `co=cogent-marketing cl=abc topic=voice-intake-config`) plus `icx=<spec version>`. Internal fleet messages keep short codes only. Each outside agent only ever receives shorthand codes for its own clients.
6. The customer table (ids, shorthand, names) and real EIN last four are PRIVATE. This repo publishes only the company shorthand table (with `XXXX` in the full code) and the topic codebook. Ship `clients.example.yaml` with fake placeholders (`id: 0000`, `short: ABC`, `name: Example Client`, `ein4: "0000"`). The validator loads a real registry from `--clients PATH` or the `ICX_CLIENTS` env var. Real registry filenames (`clients.yaml`, `clients.local.yaml`) are gitignored. Duplicate customer ids or duplicate customer shorthand in a registry are rejected.

Unknown company shorthand or full code: NAK `why=icx.co.unk`. Unknown customer shorthand, when a registry is loaded: NAK `why=icx.cl.unk`. Without a registry, a bare customer shorthand passes with a warning. Outbound lines missing `co=`, `cl=`, `topic=`, or `icx=` NAK `why=icx.ext.tok`.

## Example messages (ICOM header)

Plain English:
> Please change the inbound intake configuration for a placeholder client; the next step is the platform owner reviewing the worker.

Internal (fleet, short codes only):
```
@ENG>ICOM>OPS P1 CM.ABC #T-n ASK pr.voice.intake~cfg nx=PLATFORM:sys.wkr
```

Bare client code (still valid; resolver fills `CM` from the registry):
```
@ENG>ICOM>OPS P1 ABC #T-n ASK pr.voice.intake~cfg nx=PLATFORM:sys.wkr
```

Internal, no client (`INT0` under any company; default `IN.INT0`):
```
@ENG>ICOM>OPS P1 IN.INT0 #T-n GO org.proto
```

Outbound (leaves the fleet; plain-word tokens required):
```
@ENG>ICOM>EXT P1 CM.ABC #T-n ASK pr.voice.intake~cfg co=cogent-marketing cl=abc topic=voice-intake-config icx=1.2.0
```

ICX is about precision and routing, not compression. Word segments cost about the same tokens as numbers (`voice.intake.book` is 4 tokens and `2.31.4` is 5 in `o200k_base`), and words can be read without opening the codebook.

## Files

| Path | What |
|---|---|
| `examples/codebook.yaml` | Example codebook: companies, classes, work-state verbs, codes, facets, tombstones |
| `examples/index.yaml` | Example relative index |
| `clients.example.yaml` | Placeholder private customer registry (fake `id` / `short` / `name`, `company: CM`). Copy to `clients.yaml`. |
| `tools/icx_validate.py` | Validator: segment rules, depth, parent prefixes, verbs, facets, tombstones, index targets, company shorthand/full, customer id, outbound tokens |
| `tests/test_icx_validate.py` | Validator tests (codebook, Rule 14a slot, outbound) |

```bash
pip install pyyaml
python3 tools/icx_validate.py examples/codebook.yaml examples/index.yaml
python3 tools/icx_validate.py examples/codebook.yaml examples/index.yaml --clients clients.example.yaml
python3 tests/test_icx_validate.py
```

Optional flags: `--clients PATH` (or `ICX_CLIENTS`), `--outbound`, `--line 'ICOM header'`, `--lines FILE`.

## Changelog

- **1.2.0** (2026-11-04): Rule 14a company and client designation. Company shorthand table (`IN`/`CM`/`CD`) expands to full codes (`I-MD-XXXX`, `C-TBD-XXXX`). Private customer registry maps numeric `id` to `short` (placeholders only; real assignments TBD). `CO.CLIENT` slot, outbound `co=` `cl=` `topic=` `icx=` tokens. Spec minor bump; existing ICX object codes unchanged.
- **1.1.0** (2026-10-25): Publish ICOM work-state verbs and ICX class labels.
- **1.0.0** (2026-10-19): ICX v1 spec, example codebook and index, validator.

## Credits

ICX is an original design by Iron Noodle (2026). It draws on:

- **Dewey Decimal Classification** (Melvil Dewey, 1876): the class hierarchy, author numbers, standard subdivisions and relative index.
- **Next Concept Modeling (NCM)**, Stanford preprint, October 2026: coarse-to-fine generation where each level carries only what the level above missed.

ICX is not affiliated with OCLC, the Dewey Decimal Classification, or the NCM authors.

## License

MIT
