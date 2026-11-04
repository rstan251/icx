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

### Company codes (3)

These occupy the company prefix of the ICOM `CO.CLIENT` slot (Rule 14a).

| Code | Company | Outbound `co=` |
|---|---|---|
| `IN` | Iron Noodle LLC | `iron-noodle` |
| `CM` | Cogent Marketing LLC | `cogent-marketing` |
| `CD` | Cogent Digital LLC | `cogent-digital` |

`INT0` is the internal / no-client lane. It is valid under any company. Default: `IN.INT0`.

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

1. The CLIENT/LANE slot is `COMPANY.CLIENT`, e.g. `CM.ABC`, `IN.INT0`. Company codes (public, in the codebook under `companies`): `IN` = Iron Noodle LLC, `CM` = Cogent Marketing LLC, `CD` = Cogent Digital LLC. `INT0` = internal/no client lane, valid under any company (default `IN.INT0`).
2. Backward compatible: a bare registered client code (e.g. `ABC`) stays valid. The router/validator resolves its company from the client registry. Default parent company for clients is `CM` (Cogent Marketing) unless the registry says otherwise.
3. Routing and search work by prefix: `CM` matches all Cogent Marketing traffic, `CM.ABC` one client. The ICX object code is unchanged.
4. Client codes are added to the private registry as clients are onboarded.
5. Messages to outside agents (any ICOM line that leaves the fleet, e.g. to a partner firm's agent or a separate bot account) MUST also carry plain-word tokens `co=<company-words>` `cl=<client-words>` `topic=<topic-words>` (lowercase, hyphenated, e.g. `co=cogent-marketing cl=abc topic=voice-intake-config`) plus `icx=<spec version>`. Internal fleet messages keep short codes only. Each outside agent only ever receives its own client's name.
6. Client registry is PRIVATE: this repo publishes only the three company codes and the topic codebook, never client names or client codes. Ship `clients.example.yaml` (placeholder codes such as `ABC`/`XYZ` with `company: CM`). The validator loads a real registry from `--clients PATH` or the `ICX_CLIENTS` env var. Real registry filenames (`clients.yaml`, `clients.local.yaml`) are gitignored.

Unknown company prefix: NAK `why=icx.co.unk`. Unknown client, when a registry is loaded: NAK `why=icx.cl.unk`. Without a registry, a bare client code passes with a warning. Outbound lines missing `co=`, `cl=`, `topic=`, or `icx=` NAK `why=icx.ext.tok`.

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
| `clients.example.yaml` | Placeholder private client registry (`ABC`/`XYZ` under `CM`). Copy to `clients.yaml`. |
| `tools/icx_validate.py` | Validator: segment rules, depth, parent prefixes, verbs, facets, tombstones, index targets, company/client slot, outbound tokens |
| `tests/test_icx_validate.py` | Validator tests (codebook, Rule 14a slot, outbound) |

```bash
pip install pyyaml
python3 tools/icx_validate.py examples/codebook.yaml examples/index.yaml
python3 tools/icx_validate.py examples/codebook.yaml examples/index.yaml --clients clients.example.yaml
python3 tests/test_icx_validate.py
```

Optional flags: `--clients PATH` (or `ICX_CLIENTS`), `--outbound`, `--line 'ICOM header'`, `--lines FILE`.

## Changelog

- **1.2.0** (2026-11-04): Rule 14a company and client designation. Public `companies` (`IN`, `CM`, `CD`). `CO.CLIENT` slot, private client registry, outbound `co=` `cl=` `topic=` `icx=` tokens. Spec minor bump; existing ICX object codes unchanged.
- **1.1.0** (2026-10-25): Publish ICOM work-state verbs and ICX class labels.
- **1.0.0** (2026-10-19): ICX v1 spec, example codebook and index, validator.

## Credits

ICX is an original design by Iron Noodle (2026). It draws on:

- **Dewey Decimal Classification** (Melvil Dewey, 1876): the class hierarchy, author numbers, standard subdivisions and relative index.
- **Next Concept Modeling (NCM)**, Stanford preprint, October 2026: coarse-to-fine generation where each level carries only what the level above missed.

ICX is not affiliated with OCLC, the Dewey Decimal Classification, or the NCM authors.

## License

MIT
