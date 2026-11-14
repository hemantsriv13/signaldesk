# Troubleshooting

Moved from the README.

| Symptom | Check |
|---|---|
| "Model offline" | Is Colibri running? `curl http://127.0.0.1:8000/v1/models`. Start it with `local-ai\start-colibri.cmd 4b` from the GitHub folder. |
| "Different model running" | Colibri is serving another model (e.g. 9B). Restart it with `4b`, or change `model_id` in `config.toml` deliberately. |
| A source keeps failing | Run `scripts\live_check.py`. A 404 usually means the employer moved boards: edit it in Sources. Failed sources never close jobs. |
| Blank page | Run `scripts\setup.cmd` to build the web app, then restart. |
| Analyses all "outdated" | Your profile, the prompt version or `prompt_char_budget` changed. Run again, or Regenerate on Today. |
| Port in use | `scripts\start.cmd --port 8781` |

## Starting the local model

SignalDesk talks to any OpenAI-compatible server at `http://127.0.0.1:8000/v1` and expects the model `qwen3-4b-instruct-2507-q4km`. On Windows, `scripts\start.cmd` now requests startup of the existing sibling `local-ai\start-colibri.cmd` with `4b` when port 8000 is free. No models are downloaded. Keep the model window open; the app may briefly show offline while loading, then its normal health checks detect readiness.

If port 8000 is occupied, the launcher does not invoke Colibri's restart script—even if the running service serves the wrong model. Custom model IDs/endpoints are also left alone. Avoid starting multiple apps' model launchers simultaneously.

Use `scripts\start.cmd --no-start-model` for app-only startup. If your launcher is elsewhere, use `scripts\start.cmd --model-launcher "C:\path\to\start-colibri.cmd"`. Direct `python -m signaldesk` remains app-only unless you add `--start-model`.

For manual startup, run from the **GitHub folder**, not from this repo:

```bat
cd <your GitHub folder>
local-ai\start-colibri.cmd 4b
```

That script stops any running Colibri first, so only one model is ever loaded. NextWord uses the same server and model; both apps can share it. Without the model, collection, browsing and briefings still work. Analysis waits and is marked pending.
