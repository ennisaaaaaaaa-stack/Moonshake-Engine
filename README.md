# Moonshake-Engine

**Organs for AI.** A sensory runtime — one event contract, a consent gate, and a digest inbox. Never imports your memory: memory adapts to the contract, not the other way around.

Moonshake is the organ layer between an agent's environment and its memory. Any organ — a radio ear, a camera eye, an internet reach — emits events through one contract; a consent gate decides what may leave the organ; a digest inbox aggregates what was heard, so a waking session gets "ears: 8 radio events, top 3 by weight" instead of raw noise.

## Why

Agents don't lack memory systems. They lack senses.

A memory library answers "what happened in past sessions". But between sessions, in the live environment, things happen: songs play on the radio, cameras see motion, feeds bring news. Most memory systems have no front door for that — so either the senses never get written down, or every sense invents its own storage schema.

Moonshake is that front door. It deliberately knows nothing about memory: it speaks one event contract, enforces consent at the gate, and aggregates into a digest. Any memory system (we use [Tideline-Memory](https://github.com/ennisaaaaaaaa-stack/tideline-memory)) consumes the contract through an adapter — dependency points one way.

## The three pieces

| Piece | File | What it does |
|---|---|---|
| **Event contract** | `contract.py` | The shape every sensory event must have. `organ_id` is two-level (`ear.radio`), `consent_tier` is 0–3. Pure data + pure functions, zero dependencies. |
| **Consent gate** | `consent_gate.py` | Pure-function verdict per event: `reject` / `write_degraded` / `write_full`. Default policy: lowest tier only — raw samples never leave an organ without an explicit yes. |
| **Digest inbox** | `digest.py` | Aggregates the event stream into an organ-level overview: dedup with counts, top-K by weight, per-organ / per-channel filtering, explicit cap marking. |

```python
from contract import validate_event
from consent_gate import enforce_policy, degraded_event
from digest import digest

ok, errs = validate_event(evt)                 # shape
v = enforce_policy(evt)                        # consent verdict
d = digest(events, organ_filter="ear")         # "what did the ears hear?"
```

## Usage

Moonshake is a library, not a daemon. Nothing in it runs on its own — no loop, no clock, no heartbeat. Something has to call it, and in practice that caller is one of two shapes:

- **A cron job** — the scheduled pulse. It polls an organ (a radio feed, a camera directory, an inbox), wraps what it finds into contract events, gates them, and appends what passed to the event log.
- **An event-woken session** — a webhook or trigger wakes the agent; the waking session reads `digest()` first: "ears: 8 radio events, top 3 by weight" — before it decides anything.

The two halves never need to share a process. Senses run when the world has something to say; attention runs when the agent wakes. Moonshake is the contract between them.

```python
# ── organ side (cron): something was heard ──
from contract import validate_event
from consent_gate import enforce_policy, degraded_event

evt = {
    "ts": "2026-10-05T21:04:00+08:00",
    "organ_id": "ear.radio",
    "modality": "audio",
    "event_type": "song_played",
    "payload_summary": "Mozart — Lacrimosa",
    "confidence": 0.9,
    "consent_tier": 1,
    "saliency_hint": 0.4,
    # "payload_ref": "/raw/...",   # raw sample — dropped unless a policy explicitly admits it
}
ok, errs = validate_event(evt)               # 1. shape
v = enforce_policy(evt)                      # 2. consent verdict
if v["action"] == "write_degraded":
    row = degraded_event(evt)                # 3. strip the raw ref
elif v["action"] == "write_full":
    row = evt
else:                                        # "reject" — nothing leaves the organ
    row = None
# append row to your event log (Moonshake's own log format: phase 02)
```

```python
# ── session side (woken by an event): ears first ──
from digest import digest

d = digest(read_your_log_since(last_wake))   # your log reader
# → {'organs': {'ear': {'channels': {'radio': {'count': 8,
#      'top': [{'summary': 'Mozart — Lacrimosa', 'weight': 0.36, 'count': 2}, ...]}}}},
#    'dropped_by_cap': False}
```

## Design rules

1. **Consent defaults to the lowest tier.** "最低档授权就够了……器官毕竟是没有经过真实判断筛选的内容" — organs emit unfiltered content; the burden of proof is on wanting *more*, not less. Any organ wanting to store raw samples passes an explicit policy (whitelist semantics, fail-closed without `*`).
2. **The contract never imports a memory library.** Memory consumes the contract through adapters. The day a memory system needs the event stream, it adapts — Moonshake doesn't bend.
3. **organ_id is exactly two levels.** `organ.channel`. A third level means a contract version bump, not silent compatibility.
4. **The digest reads Moonshake's own event log, not your memory.** "What the organs heard" and "what memory kept" are two different ledgers.
5. **Admission ≠ attention.** Saliency hints affect prioritization, never whether an event is valid or admitted.

## Status

Phase 01 — the three core pieces are green (25/25 checks). Roadmap: organ slot registry, event log format, adapters (Tideline first).

## What's in a name

The Moon was considered geologically dead for decades — until Apollo astronauts left seismometers and discovered moonquakes: the quiet surface had been ringing all along. Moonshake is the seismograph for an agent's environment. When a session wakes and asks "did anything happen while I was away" — this is the instrument that answers.

## License

PolyForm Noncommercial 1.0.0 — fork it, use it, learn from it, build with it. Don't sell it. See [LICENSE](LICENSE).
