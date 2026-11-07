"""A spending limit for the paid steps, kept in budget.json in the working folder.

usage: budget.py set USD      start a limit, or change it and keep what has been spent
       budget.py              show the limit and what has been spent

Paid scripts estimate each request from the documented prices, refuse it if it would
pass the limit, and count it before it is sent, so a response lost on the way still
counts. Only a definite HTTP error gives the amount back. Requests served from the cache
cost nothing and are not counted. Without budget.json there is no limit, and each paid
script says so. These are estimates from the documentation in November 2026, not your
account's balance.
"""
import fcntl
import json
import os
import subprocess
import sys
from contextlib import contextmanager

PATH = "budget.json"
DIALOGUE_PER_1K_CHARS = 0.08  # Text to Dialogue with eleven_v4; Voice Design is billed the same way for its preview text
SCRIBE_PER_HOUR = 0.22


@contextmanager
def locked():
    """Blocks started together must not lose each other's spending."""
    with open(PATH + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def read():
    if not os.path.exists(PATH):
        return None
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def write(state):
    with open(PATH + ".tmp", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(PATH + ".tmp", PATH)


def text_cost(chars):
    return chars / 1000 * DIALOGUE_PER_1K_CHARS


def scribe_cost(audio):
    """Asks ffprobe only when a limit is set, so an unlimited run does not depend on it."""
    if read() is None:
        return 0.0
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio], capture_output=True, text=True, check=True).stdout
    return float(out) / 3600 * SCRIBE_PER_HOUR


def charge(cost, what):
    """Count a request just before it is sent, or stop the run if it would pass the limit."""
    if read() is None:
        print(f"budget: NO LIMIT, no {PATH} in {os.getcwd()}", flush=True)
        return
    with locked():
        state = read()
        if state["spent"] + cost > state["limit"]:
            raise SystemExit(f"BUDGET: {what} would cost about ${cost:.2f}, and ${state['spent']:.2f} of ${state['limit']:.2f} is spent. Nothing was sent. Raise the limit with budget.py set USD to go on.")
        state["spent"] = round(state["spent"] + cost, 4)
        write(state)
    print(f"budget: {what} about ${cost:.3f}, ${state['spent']:.2f} of ${state['limit']:.2f} spent", flush=True)


def refund(cost):
    """The server refused the request, so nothing was bought."""
    if read() is None:
        return
    with locked():
        state = read()
        state["spent"] = round(max(0.0, state["spent"] - cost), 4)
        write(state)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "set":
        with locked():
            state = read() or {"spent": 0.0}
            state["limit"] = float(sys.argv[2])
            write(state)
    elif len(sys.argv) != 1:
        raise SystemExit(__doc__)
    state = read()
    print(f"${state['spent']:.2f} of ${state['limit']:.2f} spent" if state else "no limit set")


if __name__ == "__main__":
    main()
