# KV-OptKit Program Status

Date: 2025-09-08

This file is for internal tracking. It is excluded from GitHub release source archives via `.gitattributes`.

## Phase-by-Phase Status (as of 2025-09-08)

| Phase | Status | Key Deliverables | Demos/Docs | CI/Validation | Next Actions |
|---|---|---|---|---|---|
| Phase 1 — Advisor | Complete | Advisor APIs in `kvopt/server/routers/advisor.py`; QuickView Advisor panel | `examples/demo_phase1_advisor.ps1`; `docs/README-demos.md#phase-1-advisor-recommendations-only` | Covered by SIM smoke; advisor JSON reachable | — |
| Phase 2 — Autopilot | Complete | Plan+Apply in `kvopt/server/routers/autopilot.py`; apply success/fail counters; QuickView "Enable Apply", "Apply from Advisor", Last Apply banner, applies summary | `examples/demo_phase2_autopilot.ps1`; individual action demos | Metrics-report CI performs guarded apply and asserts `kvopt_apply_success_total > 0` | — |
| Phase 3 — Policy/Governor (foundations) | Baseline in | Governor metrics in `kvopt/server/metrics.py` (e.g., `kvopt_governor_throttle_events_total`, `kvopt_offload_governed_bytes_total`) | Mentioned across docs; panels in Grafana | Visualized via Grafana; requires scenarios that trigger throttling to observe >0 | Optional: add scripted throttle scenario |
| Phase 4 — Observability & Reporting | Complete | `/metrics` (Prometheus) + `/metrics/snapshot` (JSON); QuickView JSON preview modal; Dev Hooks panel (`KVOPT_DEV=1`); applies summary; `tools/make_report.py` | `examples/demo_phase4_obs.ps1`; `docs/README-demos.md#phase-4-observability--reporting` | `.github/workflows/metrics-report.yml` does guarded apply; report generated+validated; README badges | Minor doc lint cleanup in `docs/README-demos.md` (MD009/MD012) |
| Phase 5 — Sidecar & vLLM demos | In progress (CPU flow ready; GPU-ready scaffolding) | vLLM adapter (CPU demo sequences, L2 actions); sidecar proxy scaffolding; GPU parity workflow | `docs/README-demos.md#phase-5-sidecar-and-vllm-demos` | GPU Parity CI runs when GPU present; otherwise skips | Add "Phase 5 Quick Checklist" later per preference; validate on real GPU when available |

## Platforms, Tools, and UX (as of 2025-09-08)

| Area | Status | Notes |
|---|---|---|
| QuickView | Complete | JSON Preview modal; Dev Hooks panel; applies summary line (success/fail) in `kvopt/server/routers/quickview.py` |
| CLI | Complete | `kvopt quickstart-vllm-demo`, `kvopt dev-hooks` in `kvopt/cli.py` |
| Observability Stack | Complete | `docker/compose.yml` (Grafana on 3001); dashboard JSON set to your layout in `docker/grafana-dashboard.json` |
| CI | Complete | Badges in `README.md`; smoke + metrics-report + GPU parity; metrics-report asserts real apply success |
| Docs | Complete (minor lints) | Phase 4 section in `docs/README-demos.md`; README points to Demo Guide |

## Risks/Notes

- Governor throttling remains at 0 unless a scenario triggers it; consider adding a small stress/test to exercise that path.
- Phase 5 Quick Checklist intentionally postponed; revisit later per preference.
- LMCache extracted: LMCache plugin is disabled by default and not used in Advisor/Autopilot paths. Metrics (`kvopt_reuse_hits_total`, `kvopt_reuse_misses_total`) remain defined as stubs for dashboard stability. Re-enable later via `KVOPT_LMCACHE=1` and enabling the plugin in config.

## Next Week Plan (placeholder)

- [ ] Fix minor markdown lints in `docs/README-demos.md`.
- [ ] (Optional) Add scripted governor throttle scenario and reflect in Grafana.
- [ ] (Optional) GPU-backed Phase 5.D run to validate parity + sidecar on hardware.
