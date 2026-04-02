# Dashboard Generative UI

Bundled React artifact that sits inside the local workbench dashboard and re-composes
the room into operator, research, and risk views from `/api/dashboard`.

## Files

- `src/App.tsx` - narrative generation, opportunity ranking, and control actions
- `src/App.css` - artifact-specific visual language
- `bundle.html` - single-file artifact served by `fly_entrypoint.py`

## Commands

- `npm install`
- `npm run build`
- `npm run bundle`

## Serving

The workbench serves this artifact from:

- `/artifacts/dashboard-generative-ui.html`

The main dashboard embeds that route in an iframe and also exposes a direct "Open artifact" link.
