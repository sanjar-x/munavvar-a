---
phase: 2
slug: module-convention-database-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2+ with pytest-asyncio 1.3.0+ |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/ -v --tb=short` |
| **Full suite command** | `uv run pytest tests/ -v --tb=long` |
| **Estimated runtime** | ~80 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -v --tb=short`
- **After every plan wave:** Run `uv run pytest tests/ -v --tb=long`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 80 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | ARCH-03 | unit | `uv run python -c "from src.modules.catalog.dtos import ProductDTO; print('OK')"` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | ARCH-03 | integration | `uv run pytest tests/ -v --tb=short` | ✅ | ⬜ pending |
| 02-01-03 | 01 | 1 | ARCH-02 | unit | `uv run python -c "from src.modules.catalog.public import CatalogService, ProductDTO, ProductType; print('OK')"` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | DB-01 | integration | `uv run alembic upgrade head` | ✅ | ⬜ pending |
| 02-02-02 | 02 | 2 | DB-02 | integration | `uv run pytest tests/ -v --tb=short` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `src/modules/catalog/dtos.py` — frozen DTO definitions (created by plan tasks)
- [ ] `src/modules/catalog/public.py` — facade exports (created by plan tasks)
- [ ] `src/common/types.py` — Paginated type alias (created by plan tasks)

*Wave 0 artifacts are created by plan execution tasks — no pre-existing infrastructure needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dev DB drop+recreate | DB-01 | Destructive operation | Drop DB, run `alembic upgrade head`, run `init_data()`, run full test suite |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 80s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
