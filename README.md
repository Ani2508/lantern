# Lantern

Supply planning that keeps working when the data goes dark. SparthHill Hack 2026.

**SIMULATED DATA · synthetic scenario for demonstration only**

The shared contract (names, config, DynamoDB schema, API, checkpoints) lives in the five team docs, section 2 (currently **v1.2**). This repo implements it; `lantern_core/` is the executable version of the contract.

## Quick start (Mac)

```bash
git clone <repo-url> lantern && cd lantern
bash scripts/setup_mac.sh      # installs tools, creates .venv, runs tests and the local demo
```

Then, any time:

```bash
make check        # lint + tests, before every push
make local-demo   # naive vs Lantern at hour 9, offline
make help         # every command
```

## Who owns what

| Member | Folders |
| --- | --- |
| M1 Platform & Infrastructure | `infra/`, `lantern_core/`, `api/`, `scripts/`, `.github/` |
| M2 Data, Simulator & Evaluation | `simulator/`, `ingest/`, `baselines/`, `eval/`, `tests/fixtures/` |
| M3 Forecast & Decision Engine | `engine/`, `models/` |
| M4 Safety Gate, Bedrock & Alerts | `gate/`, `explain/`, `alerts/`, `web/fallback/` |
| M5 Dashboard, Demo & Presentation | `dashboard/`, `presentation/` |

## Status

Files marked `DRAFT by M3 for <owner> review` were written ahead for that owner: review, adjust, own.

| Part | Owner | Status |
| --- | --- | --- |
| `lantern_core` (config, schemas, ids, store: local / memory / aws) | M1 | working; aws mode untested until first deploy |
| API (`api/app.py`, all routes of 2.10) | M1 | working locally (draft) |
| SAM template, Dockerfile for plan Lambda, deploy/seed/warm/kill scripts | M1 | passes cfn-lint; not deployed yet (draft) |
| Demo fixture, simulator world + generator, ingest, equal split | M2 | working (draft) |
| `features.csv` builder, evaluation + metrics, sensitivity | M2 | working (draft); full run ~6-7 min |
| Estimator, forecaster, optimizer (lantern + naive), scouts, `run_plan`, handler | M3 | working |
| Gate R1-R5 + gate log, Bedrock explain with template fallback, SNS, fallback page | M4 | working locally (draft); Bedrock/SNS untested until deploy |
| Dashboard (`dashboard/`): night map, timeline, gate moment, results, offline view, auto-play story | M5 | working on offline demo data and live API (built by M3) |
| Presentation, video | M5 | not started |

## Typical flow

```bash
make local-demo          # hour-9 story: naive REVIEW, REVIEW, BLOCK; Lantern 0 BLOCK + 2 scouts
make features train      # 200 train + 60 test scenarios -> forecaster (~1 min)
make eval SEEDS=3        # quick proof chart; plain `make eval` = 20 seeds
make api                 # http://localhost:8000/api/health
make fallback            # http://localhost:8080 - the page that survives the API going down
make dashboard           # http://localhost:5173  (?record=1 plays the story for the video)
```

## Rules

- Branches `m1/<topic>` … `m5/<topic>`; PR into `main` with one approval and green CI.
- Never commit `.env`, AWS keys or model files (models go to S3).
- Nothing in `engine/` reads `truth/`.
