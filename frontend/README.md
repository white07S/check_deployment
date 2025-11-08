# Codex-as-Chat Frontend

React single-page application that talks to the FastAPI backend for session
management and Codex streaming. TailwindCSS provides lightweight styling.

## Scripts

```bash
npm install          # install dependencies
npm start            # run the development server (http://localhost:3000)
npm run build        # production build
```

Set `REACT_APP_BACKEND_URL` to point at the FastAPI server when the frontend and
backend run on different origins:

```bash
REACT_APP_BACKEND_URL=http://127.0.0.1:8000 npm start
```

## Hard-coded identity (temporary)

Until SSO is integrated the app uses:

- `user_id = "user-123"`
- `llm_session_id` generated client-side per page load (shared across chats)

The backend enforces ownership per `user_id`, so future auth can slot in by
replacing these constants.

## UI Overview

- **Sidebar** — lists chat sessions via `GET /sessions?user_id=…` with a "New"
  button that calls `POST /sessions`.
- **Transcript** — renders persisted history from
  `GET /sessions/{id}/messages` plus live updates.
- **Reasoning panel** — streams `reasoning` payloads emitted by Codex.
- **Composer** — sends `{type: "user_message", content}` over WebSocket `/chat`.

Connection status (connecting/connected/disconnected/error) is surfaced in the
header so users can debug transport issues at a glance.

## Styling

Tailwind is configured via `tailwind.config.js` and `postcss.config.js`. All
component styles use utility classes or small `@apply` helpers in `App.css`.
