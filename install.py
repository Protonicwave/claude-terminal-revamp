"""Applies the Claude Warm terminal look to this machine, or reverses it with --uninstall."""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from installer.environment import build_environment
from installer.installing import install
from installer.model import EXIT_REFUSED, Host, InstallerError, Report
from installer.runner import run_command
from installer.uninstalling import uninstall


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true", help="reverse what install applied")
    options = parser.parse_args(argv)
    host = Host(
        platform=sys.platform,
        env_vars=dict(os.environ),
        home=Path.home(),
        python_executable=sys.executable,
        now=datetime.now(),
    )
    try:
        env = build_environment(host, Path(__file__).parent, run_command)
        report: Report = uninstall(env) if options.uninstall else install(env)
    except InstallerError as err:
        print(f"Nothing was changed. {err}")
        return EXIT_REFUSED
    print("\n".join(report.lines))
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
