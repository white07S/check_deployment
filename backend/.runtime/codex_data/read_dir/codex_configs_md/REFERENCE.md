# Reference Notes

- The workspace that Codex edits lives under `workspace/` in the session
  directory. Treat this as the active project root unless the user specifies
  otherwise.
- Shared, read-only resources (documentation, fixtures, examples) are mounted
  beneath `codex_configs_md/` and other siblings inside `DATA_READ_DIR`. These
  are safe to read but **must not** be modified.
- When running commands, prefer `just`, `npm`, or `python` scripts that already
  exist in the repository before introducing new tooling.
- For long-running operations, provide incremental updates so the user keeps
  track of progress.
