<!-- intention: a Chinese-language repository → the same repository with all human-readable prose in English, behaviour unchanged, tests green -->

# English localization of Daofy (2026-11-20)

## Goal

Translate every human-readable Chinese text in this repository into English — source
comments, docstrings, log lines, tool descriptions, user-facing messages, agent rule
resources, tests and project documentation — without changing behaviour.

Request, quoted: «перевести этот проект на английский язык» · «Ну и оформить по нашим правилам».

## Acceptance record (G0)

| id | criterion | oracle | verdict |
|----|-----------|--------|---------|
| C1 | No Chinese prose remains in the translated surfaces (source, resources, tests, docs, entry files) | `grep \p{Han}` per surface, count 0 outside the declared data exceptions | — |
| C2 | Behaviour unchanged: the test suite's pass/fail set equals the pre-change baseline | `pytest -q` before and after, failure inventory compared | — |
| C3 | Python sources still compile | `python -m compileall src tests` | — |
| C4 | Doc-consistency guards keep their intent, expressed against the English wording | `tests/test_doc_consistency.py` green | — |
| C5 | The work is recorded: plan + progress log + glossary of Daofy terms | this file, `_progress_log.md` | — |

Failure (derived as the negation): Chinese prose still present in a surface claimed done, or
the suite's result changed for a reason other than the translation.

## Declared exceptions (data, not prose)

These keep Chinese on purpose; translating them would change what is tested or displayed.

1. **Encoding test data** — strings written to prove GBK/Big5/UTF-16 handling
   (`tests/test_encode_action.py`, `tests/test_file_backup.py`, `tests/test_file_tool.py`
   `中文` cases). The Chinese text *is* the fixture.
2. **Fixture captions of pre-existing demo applications** — control names in
   `tests/scripts/*.json`, `tests/冒烟测试/*.json`, `docs/tutorial/**` that address a demo UI
   whose own sources are not translated in this change.
3. **Delphi/Pascal sources** (`tools/auto/*.pas`, `tools/stacktrace/*.pas`,
   `docs/tutorial/**/*.pas`) — the project rule requires `delphi_file` for every read/write of
   these suffixes and that tool is not reachable from this session. Residual, see below.

## Method (per module)

For each module the code, its tests and its documentation are translated **together**, because
154 test assertions compare against Chinese strings the tools emit.

1. Translate comments, docstrings, log lines and user-facing messages into idiomatic technical
   English. Identifiers, dict keys, JSON field names, command names, API names, paths, code
   samples and regexes stay byte-identical.
2. Never translate text that is *data* (see exceptions), and never change a code path.
3. Run the module's tests; the oracle is that they still pass with the assertions updated to the
   new English wording, with the same intent.

## Status (measured 2026-11-20T19:00Z)

Han-character counts, `grep \p{Han}`; the tool output is the source of truth, not prose.

| Surface | Before | Now | Note |
|---|---|---|---|
| `README.md` | 6,900 | 0 | ✓ |
| `AGENTS.md` | 4,500 | 0 | ✓ |
| `src/tool_docs.py` | 1,006 | 23 | ✓ |
| `src/server.py` | 414 | 0 | ✓ |
| `src/resources/**` | 56,410 | ~700 | ✓ (residual Chinese sample captions) |
| `docs/**` | 80,644 | 29,308 | 20 documents done; tutorials + `.pas` assets open |
| `src/tools/**` | 37,223 | ~130 | ✓ |
| `src/services/**` | 29,835 | 900 | ✓ except `copyright_service.py` (652) |
| `src/utils/**` | 6,711 | ~400 | `updater.py`, `file_backup.py`, `dproj_parser.py` open |
| `src/plugins/**` | 4,161 | 0 | ✓ |
| `tests/**` | 24,503 | 23,921 | assertions aligned; comments still Chinese |
| `CHANGELOG.md` | 711 | 711 | restored: the model condensed 45 version sections to 30 |
| `tools/**/*.pas` | 5,450 | 5,450 | blocked: `delphi_file` unreachable |

### Method that works (measured)

`aicall` with `model=deepseek-v4.1-flash`, `provider=opencode-go`, one file or one
fragment per call, `output_file` under `.temp/i18n/`, then a byte-level join. Fragments
must be cut at whole statement or heading boundaries (`.temp/i18n/split_dict.py`,
`split_py.py`, `split_file.py`) and the join must guarantee a newline between fragments.
`max_tokens` 20,000-32,000 is required: below that the completion comes back empty.

### Remaining work

- [ ] `src/tools/**` — 24 files still Chinese (largest: `file_tool.py` 752)
- [ ] `src/services/**` — 22 files (largest: `copyright_service.py` 652, `compiler_service.py` 537)
- [ ] `src/plugins/**` — 13 files (the plugin layer feeds MCP tool descriptions)
- [ ] `src/utils/**` — 5 files (`updater.py` 194, `file_backup.py` 110, `dproj_parser.py` 97)
- [ ] `docs/**` — 34 documents (tutorial 1,154 + 692; design plans open)
- [ ] `CHANGELOG.md` — 711
- [x] Test oracle — final run 1,650 cases, 373 bad vs 390 at baseline, **0 new failures**, 17 previously failing now pass (`.temp/final3.xml`)
- [ ] `tests/**` — comments plus ~154 assertions quoting Chinese message text
- [ ] `tools/**/*.pas` and `docs/tutorial/**/*.pas` — needs `delphi_file`, unavailable here


## Glossary (keep one English term per Chinese term)

| Chinese | English |
|---|---|
| 知识库 | knowledge base (KB) |
| 编译 | compile / build |
| 单元 | unit |
| 工程 / 项目 | project |
| 组件 | component |
| 控件 | control |
| 源码 | source |
| 备份 | backup |
| 脏标记 | dirty flag |
| 行号 | line number |
| 格式化 | format |
| 编码 | encoding |
| 乱码 | garbled text |
| 自动化测试 | automation testing |
| 脚本 | script |
| 布局 | layout |
| 审计 | audit |
| 经验库 | experience library |
| 三方库 | third-party library |
| 工具 | tool |
| 返回值 | return value |
| 参数 | parameter / argument |
| 调用 | call / invoke |
| 编排 | orchestration |
| 黑盒 | black-box |
| 白盒 | white-box |
| 冒烟测试 | smoke test |
| 回归 | regression |
| 指纹 | fingerprint |
| 增量 | incremental |
| 全量 | full |

## Smoke contract

- Baseline: `pytest -q` on the untouched tree (run-1, started 2026-11-20T14:46Z).
- After: `pytest -q` and `python -m compileall src tests`; differences classified one by one.
- Post-change oracle for C1: `grep -c \p{Han}` per surface, stated per file.
