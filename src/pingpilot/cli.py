import argparse
import logging
import sys
from collections import Counter

from . import control
from .config import Settings
from .exceptions import ConfigError, Fatal, Stop
from .factory import build_channel, build_source
from .journal import Journal
from .logging_setup import setup_logging
from .messages import build_message_provider
from .models import Status
from .runner import Runner

log = logging.getLogger("pingpilot")


def build_parser():
    p = argparse.ArgumentParser(prog="pingpilot", description="Resilient, resumable outreach automation")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="send to every pending contact")
    run.add_argument("--source", choices=["sheet", "csv"])
    run.add_argument("--csv", dest="csv_path", help="CSV path (implies --source csv)")
    run.add_argument("--channel", choices=["whatsapp_web", "dry_run"])
    run.add_argument("--dry-run", action="store_true", help="walk the pipeline without sending")
    run.add_argument("--max", type=int, dest="max_per_run", help="cap sends in this run")

    st = sub.add_parser("status", help="show counts per status")
    st.add_argument("--source", choices=["sheet", "csv"])
    st.add_argument("--csv", dest="csv_path")
    return p


def cmd_run(settings):
    control.install_signal_handlers()
    runner = Runner(
        source=build_source(settings),
        channel=build_channel(settings),
        messages=build_message_provider(settings),
        settings=settings,
        journal=Journal(settings.journal_path),
    )
    runner.run()
    return 0


def cmd_status(settings):
    counts = Counter()
    for c in build_source(settings).load():
        counts[c.status.value if c.status else "Pending"] += 1
    width = max([len(k) for k in counts] + [7])
    for k in ["Pending"] + [s.value for s in Status]:
        if counts.get(k):
            print(f"{k:<{width}}  {counts[k]}")
    print(f"{'Total':<{width}}  {sum(counts.values())}")
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    overrides = {
        "source": "csv" if getattr(args, "csv_path", None) and not args.source else args.source,
        "csv_path": getattr(args, "csv_path", None),
        "channel": "dry_run" if getattr(args, "dry_run", False) else getattr(args, "channel", None),
        "max_per_run": getattr(args, "max_per_run", None),
    }
    settings = Settings.from_env(**overrides)
    setup_logging(settings.log_file)
    try:
        settings.validate(need_message=args.cmd == "run")
        return cmd_run(settings) if args.cmd == "run" else cmd_status(settings)
    except ConfigError as e:
        log.error("Config error: %s", e)
        return 2
    except Stop:
        log.info("Stopped. Re-run to resume where you left off.")
        return 0
    except Fatal as e:
        log.error("Aborted: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
