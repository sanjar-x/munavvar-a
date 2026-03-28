---
phase: 1
slug: characterization-tests
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2+ with pytest-asyncio 1.3.0+ |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/ -v --tb=short` |
| **Full suite command** | `uv run pytest tests/ -v --tb=long` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -v --tb=short`
- **After every plan wave:** Run `uv run pytest tests/ -v --tb=long`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | TEST-01..04 | infra | `uv run pytest tests/ --collect-only` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 2 | TEST-01 | integration | `uv run pytest tests/integration/test_delivery_fulfillment.py -v` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 2 | TEST-02 | integration | `uv run pytest tests/integration/test_warehouse_pickup.py -v` | ❌ W0 | ⬜ pending |
| 01-02-03 | 02 | 2 | TEST-03 | integration | `uv run pytest tests/integration/test_walkin_sale.py -v` | ❌ W0 | ⬜ pending |
| 01-02-04 | 02 | 2 | TEST-04 | integration | `uv run pytest tests/integration/test_shift_close.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — savepoint-based session fixtures, AsyncClient, auth helpers
- [ ] `tests/factories/` — entity factory functions for products, users, inventories, orders
- [ ] `tests/integration/` — directory structure for integration tests

*Wave 0 builds the entire test infrastructure since zero tests exist.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
