"""Launch the long-lived CloakBrowser instance every task attaches to."""

import os
import signal
import sys
from pathlib import Path

from cloakbrowser import launch_persistent_context

PROFILE = Path(os.environ.get("CLOAK_PROFILE_DIR", "~/.cloak-automation-profile")).expanduser()
PORT = int(os.environ.get("CLOAK_CDP_PORT", "9222"))
# Headed by default so captchas / 2FA / login walls are visible. Tasks must
# never call page.bring_to_front() — the window sits quietly on another desktop
# without stealing focus. Set CLOAK_HEADED=0 to run fully headless.
HEADED = os.environ.get("CLOAK_HEADED", "1").lower() in ("1", "true", "yes")


def main() -> None:
    PROFILE.mkdir(parents=True, exist_ok=True)
    print(f"Profile : {PROFILE}")
    print(f"CDP     : http://localhost:{PORT}")
    print(f"Mode    : {'headed' if HEADED else 'headless'}")
    if HEADED:
        print("(set CLOAK_HEADED=0 next time to run headless and stay out of your way)")
    else:
        print("(set CLOAK_HEADED=1 if you need to interactively log in / solve a captcha)")
    print("Launching CloakBrowser...")

    ctx = launch_persistent_context(
        str(PROFILE),
        headless=not HEADED,
        humanize=False,  # launcher is just a host; tasks opt in per page
        args=[f"--remote-debugging-port={PORT}"],
    )
    print("Ready. Press Ctrl-C to quit.")

    def shutdown(*_):
        try:
            ctx.close()
        finally:
            sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    signal.pause()


if __name__ == "__main__":
    main()
