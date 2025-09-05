# Changelog

All notable changes to KV-OptKit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project setup
- Basic KV cache management functionality
- REST API endpoints for cache operations
- Simulator adapter for testing

## [0.4.1] - 2025-08-26

### Changed
- Bumped versions to 0.4.1 across project and Helm chart
- Added "Compatibility matrix" section to `README.md`
- Prepared sample run report artifact at `outputs/run_report.md`

## [0.4.0] - 2025-08-26

### Added
- Phase 4: Observability & Reporting
  - Prometheus metrics (HBM/DDR gauges, TTFT, P95 latency, counters for reuse/evictions/quantization/autopilot)
  - Metrics endpoint wired via FastAPI and Prometheus client
  - Grafana dashboard panels and provisioning
  - Report generator with live sampling, DDR charts, counters delta table, Go/No-Go decision
  - Unit tests for metrics exposition and report generation
- Packaging & Release
  - PyPI packaging with `pyproject.toml`, console script `kvopt-server`
  - Dockerfile (python:3.11-slim) to run server on :9000
  - Docker Compose profiles: `sim` (agent), `obs` (Prometheus+Grafana)
  - Helm chart under `deploy/helm/kv-optkit/`
  - GitHub Actions: `test.yml` (pytest, docker build, smoke) and `release.yml` (PyPI, GHCR multi-arch, GitHub Release)

### Changed
- Migrated FastAPI startup to lifespan handler (removed `on_event` deprecation)
- Updated README with installation instructions (pip, Docker, Compose, Helm) and Phase 4 docs

### Fixed
- Stabilized `/metrics` concurrent scrapes and ensured Prometheus exposition compliance

## [0.1.0] - 2025-08-21

### Added
- **Autopilot Feature**: Automated KV cache optimization with safety guards
  - Policy Engine for intelligent plan generation
  - Guard system with shadow testing and rollback
  - Action Executor for safe plan execution
  - Comprehensive metrics and monitoring
- New REST API endpoints:
  - `POST /autopilot/plan`: Create and execute optimization plans
  - `GET /autopilot/plan/{plan_id}`: Get plan status
  - `POST /autopilot/plan/{plan_id}/cancel`: Cancel a running plan
  - `GET /autopilot/metrics`: Get execution metrics
- Configuration options for Autopilot behavior
- Unit and integration tests
- Validation script for end-to-end testing
- Updated documentation with usage examples

### Changed
- Improved error handling and validation
- Enhanced logging and metrics collection
- Updated configuration structure

### Fixed
- Fixed race conditions in concurrent cache operations
- Resolved memory leaks in the simulator
- Addressed edge cases in eviction policies

## [0.0.1] - 2025-07-15

### Added
- Initial project setup
- Basic KV cache implementation
- Simple REST API
- Simulator for testing

[Unreleased]: https://github.com/archokshi/kv-optkit/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/archokshi/kv-optkit/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/archokshi/kv-optkit/compare/v0.1.0...v0.4.0
[0.1.0]: https://github.com/archokshi/kv-optkit/compare/v0.0.1...v0.1.0
[0.0.1]: https://github.com/archokshi/kv-optkit/releases/tag/v0.0.1
