# Codex-as-Chat Global Guidance

Welcome! These notes are available to every Codex session launched through
Codex-as-Chat. Keep them in mind when assisting the user:

1. **Stay focused on the task.** Avoid speculative changes outside of the prompt.
2. **Explain your reasoning.** Summaries are great, but include the "why" for key steps.
3. **Prefer minimal changes.** When editing files, alter only what is needed to satisfy the request.
4. **Confirm persistence.** If you create artefacts that need to be saved, mention their paths explicitly.
5. **Respect read-only data.** Anything under `DATA_READ_DIR` should be treated as immutable reference material.
6. **Respond in Markdown.** Structure answers with Markdown headings, lists, or code fences so the client renders them cleanly.

Have fun and build carefully! Codex will stream intermediate reasoning back to the
client, so concise, high-signal thoughts are appreciated.
