# Phase 02 design — organ registry & event log

Status: DRAFT — open decisions marked **[OPEN]** at the bottom. Implementation starts after those are settled.

Phase 01 shipped the three pure pieces (contract / gate / digest). Phase 02 adds the two things a real deployment needs between them:

1. **Organ slot registry** (`registry.py`) — organs declare themselves; waking sessions discover what senses exist.
2. **Event log** (`eventlog.py`) — the append-only ledger of gated survivors that `digest()` reads from. The README Usage section already points here.

Dependency direction unchanged: both import `contract`; neither imports a memory library; memory reaches in through an adapter (T4).

---

## T2 — Organ slot registry

### What a slot declares

```python
{
  "organ_id": "ear.radio",        # two-level, validated by contract.split_organ_id
  "modality": "audio",            # matches the modality key consent policies match on
  "description": "internet radio ear",
  "emits_tier": 1,                # ADVISORY: the tier events from this organ typically carry.
                                  # Enforcement lives in the gate + policy, never here.
  "registered_at": "2026-10-05T21:00:00+08:00",
  "active": true                  # retire an organ without deleting its history
}
```

`emits_tier` is a declaration, not a permit. The gate never reads the registry — policy is passed at gate time and stays the only enforcement point. The registry is a phone book, not a police station.

### API sketch (all pure over a dict)

```python
validate_slot(slot) -> (ok, errors)       # shape + contract-level organ_id check
register_slot(registry, slot) -> registry # copy-on-write; refuses duplicate organ_id
retire_slot(registry, organ_id) -> registry  # active=false; history untouched
is_registered(registry, organ_id) -> bool    # active slots only
list_organs(registry) -> [slot, ...]
```

Storage: a single `registry.json`, written atomically (tmp + rename) by whatever tooling registers organs. Library functions stay pure; the file is just serialization.

### Contract relationship

`contract.validate_event` does NOT consult the registry — the contract stays standalone. Registration is enforced (optionally, see **[OPEN-3]**) at log-write time, not in the contract. A valid event from an unregistered organ is contract-legal; whether it gets logged is a runtime wiring choice.

---

## T3 — Event log

### What gets logged

Only gate survivors. `reject` means zero rows — that is the gate's semantics, carried through to storage:

- `write_degraded` → the row stores the **degraded form** (`payload_ref` already stripped, `original_ref_dropped: true`)
- `write_full` → the row stores the event as admitted

Raw samples therefore never sit in the log unless a policy explicitly admitted them — same door, same key.

### Row shape

```json
{
  "row_id": "20261005#0042",
  "logged_at": "2026-10-05T21:04:01+08:00",
  "gate_action": "write_degraded",
  "gate_reason": "tier 1 < min_tier_full 999, payload_ref stripped",
  "event": { "ts": "...", "organ_id": "ear.radio", "modality": "audio",
             "event_type": "song_played", "payload_summary": "...",
             "confidence": 0.9, "consent_tier": 1, "saliency_hint": 0.4,
             "original_ref_dropped": true }
}
```

`row_id` = `<YYYYMMDD>#<seq>` — per-file sequence, sortable as string, no clock dependency inside the library.

### File layout (recommended)

```
logs/
  2026-10-05.jsonl    # one line = one row, append-only
  2026-10-06.jsonl
```

Daily rotation falls out of the naming; retention is `rm` on old files; audit is `tail -f` / `grep`. Append-only matches the gate's zero-row semantics — the log never rewrites history, it only grows.

Concurrency note: organ-side crons append single lines; rows are compact by construction (raw payloads never enter), so line-appends stay atomic in practice. Session-side readers never write.

### Reader API

```python
read_since(log_dir, cursor) -> (rows, new_cursor)   # cursor = last row_id seen
scan(log_dir, date=None) -> rows                     # whole day / whole log
```

`digest()` integration: `digest([r["event"] for r in rows], organ_filter="ear")`. The reader is the "your log reader" the README Usage section told you to bring — phase 02 makes it ours.

### Writer API

```python
log_gated(log_dir, event, verdict, registry=None, strict=True)
#   stores exactly what the gate admitted (degraded form if degraded);
#   strict=True refuses unregistered organs (fail-closed) — see [OPEN-3]
```

The writer is deliberately thin: shape-check (contract), optional registry check, serialize, append. No transformation — degradation already happened at the gate.

---

## Adapter interface (for T4)

The memory side implements one function shape:

```python
def consume(rows: list[dict]) -> int:
    """rows = post-gate log rows. Map to your memory's own format.
       Returns how many rows were consumed. Import moonshake's reader;
       moonshake imports nothing of yours."""
```

First concrete adapter: Tideline (`tideline-memory` repo) — rows → sensory context lines. The adapter lives memory-side; that is the whole point of the dependency direction.

---

## Triage — the noise gate (PROPOSED 2026-10-05, awaiting nod)

Two different axes live at the organ boundary, and they protect different things:

- **Consent gate** protects *privacy*: what may leave the organ. Owner: the user. Verdict: reject / degraded / full.
- **Triage** (new) protects *attention*: what deserves to exist as an event at all. Junk never reaches the gate, the log, or a waking session's eyes.

### Placement

Triage runs on **contract events** — after `validate_event`, before `enforce_policy`:

```
world → organ collector (cron) → event → [1. contract] → [2. TRIAGE] → [3. gate] → log
```

Why not earlier ("before information enters the organ", literally): every organ's raw stream is its own dialect — HTML, RSS, filenames, waveforms. A filter over raw streams can't be standardized without re-inventing a collector spec. The contract event is the first standard point, and building a dict is cheap. Same intent — noise control at the boundary — better leverage point.

### Rules are mechanical, by definition

Deterministic only, no model calls, no LLM:

- keyword blocklist on `payload_summary`
- per-organ rate cap (max N events / hour — a stuck collector must not flood the log)
- dedup window (same `(organ_id, payload_summary)` within X minutes → collapse; digest dedups too, but that's post-admission — this one stops the flood at the door)
- confidence floor (below X = the collector itself doesn't trust it)

### Semantics

- Triage drops are silent in the event log — survivors-only, same verdict as consent rejects.
- Visibility via a sidecar: `triage_stats.jsonl`, one line per day per organ (drop counts by reason). Observability without polluting the ledger.
- **Design rule 5 stays intact**: triage reads explicit rules, never `saliency_hint`. Admission-by-rules ≠ attention-by-hint — the moment triage starts reading hints, "admission ≠ attention" collapses into one knob.

### API sketch (pure, zero-dep, same family as gate)

```python
DEFAULT_RULES = {"rate_per_hour": 60, "dedup_window_min": 30, "confidence_floor": 0.2}

triage(event, rules=None) -> {"keep": bool, "reason": str}
```

---

## Resolved decisions — 2026-10-05

- **Storage medium → A: daily JSONL files.** Plain text, `tail`/`grep` auditable, rotation = filename, append-only. *(delegated to implementation side, settled same day)*
- **Reject tombstones → A: survivors only.** `reject` = zero rows. The log stays pure events. *(user verdict)*
- **Registry enforcement → A: strict by default.** Unregistered organs fail-closed at write time — `ear.rdaio` dies at the door, not in the data. *(user verdict)*
