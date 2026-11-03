"""Start SignalDesk:  python -m signaldesk  [--port 8780] [--open]"""
from __future__ import annotations

import argparse
import ipaddress
from pathlib import Path
import sys
import webbrowser

import uvicorn

from .config import load_config
from .db import DB
from .engine import Engine
from .llm import LocalModel
from .netsafe import Fetcher
from .scheduler import Scheduler
from .startup import start_local_model
from .seeds import seed
from .server import WEB, create_app, setup_logging


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="signaldesk")
    ap.add_argument("--home", help="data directory (default: %%SIGNALDESK_HOME%% or D:/LocalAI/signaldesk)")
    ap.add_argument("--port", type=int)
    ap.add_argument("--open", action="store_true", help="open the app in the browser")
    ap.add_argument("--start-model", action="store_true", help="start the existing Windows Colibri 4B launcher if port 8000 is free")
    ap.add_argument("--no-start-model", action="store_true", help="open SignalDesk without starting Colibri")
    ap.add_argument("--model-launcher", type=Path, help="path to your existing start-colibri.cmd")
    args = ap.parse_args(argv)
    cfg = load_config(args.home)
    if args.port:
        cfg.server.port = args.port
    host = cfg.server.host
    if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
        print(f"Refusing to listen on {host}: SignalDesk has no login and must stay on this computer (use 127.0.0.1).")
        return 2
    if args.start_model and not args.no_start_model:
        print(start_local_model(cfg.model, args.model_launcher), flush=True)
    setup_logging(cfg.logs_dir)
    db = DB(cfg.db_path)
    seed(db)
    engine = Engine(cfg, db, LocalModel(cfg.model), Fetcher(cfg.fetch))
    scheduler = Scheduler(engine)
    scheduler.thread.start()
    app = create_app(engine, scheduler)
    url = f"http://{host}:{cfg.server.port}/"
    print(f"SignalDesk data: {cfg.home}")
    print(f"Model server: {cfg.model.base_url} (expects {cfg.model.model_id}); {engine.check_model()['message']}")
    if not WEB.exists():
        print("The web app is not built yet: run  cd web && npm install && npm run build  (the API still works).")
    print(f"Open {url}")
    if args.open:
        webbrowser.open(url)
    uvicorn.run(app, host=host, port=cfg.server.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
