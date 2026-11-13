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


def sweep_main(argv) -> int:
    from . import sweep
    ap = argparse.ArgumentParser(prog="signaldesk sweep", description="Run one sweep now (the same entry point the app and the scheduled task use).")
    ap.add_argument("--home", help="data directory")
    ap.add_argument("--scope", default="full", help="full | jobs | funding | contacts | reading | source:KEY")
    ap.add_argument("--trigger", default="manual", choices=["manual", "schedule", "catch-up"])
    ap.add_argument("--wait-minutes", type=int, default=90, help="how long to wait for analysis when running without the app")
    ap.add_argument("--start-model", action="store_true", help="start the existing Colibri 4B launcher first if port 8000 is free")
    args = ap.parse_args(argv)
    cfg = load_config(args.home)
    setup_logging(cfg.logs_dir)
    if args.start_model:
        print(start_local_model(cfg.model, None), flush=True)
    try:
        return sweep.main(cfg, args.scope, args.trigger, args.wait_minutes)
    except ValueError as e:
        print(e)
        return 2


def auth_main(argv) -> int:
    """python -m signaldesk auth set-password | status | revoke-sessions | revoke-panel"""
    import getpass
    from . import auth
    ap = argparse.ArgumentParser(prog="signaldesk auth")
    ap.add_argument("action", choices=["set-password", "status", "revoke-sessions", "revoke-panel"])
    ap.add_argument("--home", help="data directory")
    args = ap.parse_args(argv)
    cfg = load_config(args.home)
    if args.action == "set-password":
        first = getpass.getpass("New SignalDesk password (12+ characters, not shown): ")
        if first != getpass.getpass("Repeat it: "):
            print("The two entries differ. Nothing changed.")
            return 1
        try:
            auth.set_password(cfg.auth_path, first)
        except ValueError as e:
            print(e)
            return 1
        db = DB(cfg.db_path)
        n = auth.revoke_sessions(db)
        print(f"Password saved as a scrypt hash in {cfg.auth_path}. {n} existing session(s) signed out.")
        return 0
    db = DB(cfg.db_path)
    if args.action == "revoke-sessions":
        print(f"Signed out {auth.revoke_sessions(db)} session(s).")
    elif args.action == "revoke-panel":
        print(f"Revoked {auth.revoke_panel_token(db)} side-panel token(s).")
    else:
        print(f"Password set: {auth.password_set(cfg.auth_path)} ({cfg.auth_path})")
        print(f"Active sessions: {len(auth.list_sessions(db))}")
        print(f"Active side-panel tokens: {sum(1 for t in auth.list_panel_tokens(db) if not t['revoked_at'])}")
        print(f"LAN mode in config: {cfg.lan.enabled} (bind {cfg.lan.bind or 'not set'}, port {cfg.lan.port})")
    return 0


async def _serve(configs) -> None:
    import asyncio
    servers = [uvicorn.Server(c) for c in configs]
    await asyncio.gather(*(s.serve() for s in servers))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "sweep":
        return sweep_main(argv[1:])
    if argv and argv[0] == "auth":
        return auth_main(argv[1:])
    ap = argparse.ArgumentParser(prog="signaldesk")
    ap.add_argument("--lan", action="store_true", help="also serve signed-in HTTPS on this PC's home-network address (see docs/LAN_AND_PANEL.md)")
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
        print(f"Refusing to listen on {host}: the plain HTTP app stays on this computer (use 127.0.0.1). "
              "For your phone, use LAN mode, which serves signed-in HTTPS only: python -m signaldesk --lan")
        return 2
    use_lan = args.lan or cfg.lan.enabled
    if use_lan:
        from .lan import check
        errors, warnings = check(cfg)
        for w in warnings:
            print(f"Warning: {w}")
        if errors:
            print("LAN mode was not started. Nothing listens on your network until these are fixed:")
            for e in errors:
                print(f"  - {e}")
            print("To run on this PC only, start without --lan (and set [lan] enabled = false).")
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
    app.state.delivery.thread.start()
    url = f"http://{host}:{cfg.server.port}/"
    print(f"SignalDesk data: {cfg.home}")
    print(f"Model server: {cfg.model.base_url} (expects {cfg.model.model_id}); {engine.check_model()['message']}")
    if not WEB.exists():
        print("The web app is not built yet: run  cd web && npm install && npm run build  (the API still works).")
    print(f"Open {url}")
    if args.open:
        webbrowser.open(url)
    local = uvicorn.Config(app, host=host, port=cfg.server.port, log_level="warning", proxy_headers=False, server_header=False)
    if not use_lan:
        uvicorn.Server(local).run()
        return 0
    lan = uvicorn.Config(app, host=cfg.lan.bind, port=cfg.lan.port, log_level="warning", proxy_headers=False, server_header=False,
                         ssl_certfile=cfg.lan.cert_file, ssl_keyfile=cfg.lan.key_file)
    names = ", ".join(f"https://{h}:{cfg.lan.port}/" for h in cfg.lan.hostnames)
    print(f"LAN entry point (sign-in required): {names}. The app and Colibri stay on loopback.")
    import asyncio
    asyncio.run(_serve([local, lan]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
