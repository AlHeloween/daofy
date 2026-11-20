# Progress log

One entry per bounded task. Newest first.

## 2026-11-20 — English localization, wave 1

**Task**: translate the repository's Chinese prose to English (plan:
`plans/2026-11-20_english-localization.md`).

**Done (measured with `grep \p{Han}`)**

- `README.md` 6,900 → 0; `AGENTS.md` 4,500 → 0.
- `src/tool_docs.py` 1,006 → 92; `src/server.py` 414 → 73 (residual: Chinese
  trigger words kept on purpose, e.g. `【仅限 Delphi】`).
- `src/resources/**` 56,410 → most of the tree; every `coding-rules/**` document,
  the automation reference set and the scenario set are English.
- `docs/` — 12 documents translated (`tool_help`, `delphi_file`, `delphi_kb`,
  `manage_component`, `check_environment`, `get_coding_rules`, `code_hosting`,
  `project`, `configuration`, `debug_guide`, `experience-knowledge-base`,
  `automate_test_guide`, `async_task`, `package`).
- `src/plugins/delphi/handlers.py`, `src/mcp_compat.py`, `src/mcp_resources.py`
  (the MCP description surface) are English.

**Method (the one that worked)**

`aicall`, `model=deepseek-v4.1-flash`, `provider=opencode-go`, one file or one
boundary-aligned fragment per call, `output_file` under `.temp/i18n/`, then a
byte-level join. `task`-delegation (`coder_agent`) reports `failed: undefined`
on this host while sometimes doing the work in the background — not usable as a
controlled instrument. `max_tokens` below ~20,000 returns an empty completion.

**Test oracle**

Baseline captured before any change: 1,650 cases, 390 bad, 73 skipped
(`.temp/baseline.xml`). The suite cannot be green as a whole in this environment:
`zvec`, `daudit` and `pytest-asyncio` are missing at baseline (18 collection
errors + 390 failures before any edit). After wave 1 the suite reports 1,650 cases,
373 bad, **0 new failures**, 17 previously failing tests now pass (`.temp/final3.xml`
against `.temp/baseline.xml`).

**Open**

- `src/tools/**` 24 files, `src/services/**` 22 files, `src/utils/**` 5 files,
  `src/plugins/**` remaining 11 files.
- `docs/**` 34 documents, `CHANGELOG.md` (711).
- `tests/**` comments and ~154 assertions that quote Chinese message text.
- `tools/**/*.pas` and `docs/tutorial/**/*.pas` — blocked: `delphi_file` is not
  reachable from this session, and editing `.pas` with native tools is forbidden
  by `AGENTS.md`.
