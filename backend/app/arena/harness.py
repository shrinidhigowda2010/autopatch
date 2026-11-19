"""Runs inside the sandbox. Calls one function with every attack input and reports what happened.

Usage: python _fixpilot_attack.py MODULE_PATH CLASS_NAME FUNC_NAME  (cases in _fixpilot_cases.json)
This file is copied into a scratch folder; it never runs in the FixPilot server process.
"""

import importlib.util
import inspect
import json
import os
import signal
import sys
import traceback

MARKER = "FIXPILOT_RESULTS "
SAFE_BUILTINS = {
    name: getattr(__builtins__, name, None) if not isinstance(__builtins__, dict) else __builtins__.get(name)
    for name in ("float", "int", "str", "list", "range", "dict", "set", "tuple", "bytes")
}


class Hung(Exception):
    pass


def _on_alarm(*_args):
    raise Hung()


def _load(module_path):
    spec = importlib.util.spec_from_file_location("fixpilot_target", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _callable(module, class_name, func_name):
    if not class_name:
        return getattr(module, func_name)
    cls = getattr(module, class_name)
    needed = [
        param
        for param in inspect.signature(cls).parameters.values()
        if param.default is param.empty and param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
    ]
    return getattr(cls(*["attacker"] * len(needed)), func_name)


def _short(value):
    try:
        text = repr(value)
    except Exception:  # noqa: BLE001
        text = "<unprintable>"
    return text if len(text) <= 120 else text[:117] + "..."


def main():
    module_path, class_name, func_name = sys.argv[1], sys.argv[2], sys.argv[3]
    real_module = os.path.realpath(module_path)
    with open("_fixpilot_cases.json", encoding="utf-8") as handle:
        cases = json.load(handle)
    try:
        module = _load(module_path)
    except BaseException as exc:  # noqa: BLE001
        print(MARKER + json.dumps({"import_error": f"{type(exc).__name__}: {exc}"[:300]}))
        return
    signal.signal(signal.SIGALRM, _on_alarm)
    results = []
    for case in cases:
        try:
            values = [eval(expr, {"__builtins__": SAFE_BUILTINS}) for expr in case["args"]]  # noqa: S307
        except Exception as exc:  # noqa: BLE001
            results.append({"status": "skipped", "detail": f"Bad input: {exc}"[:150]})
            continue
        signal.alarm(2)
        try:
            outcome = _callable(module, class_name, func_name)(*values)
            signal.alarm(0)
            results.append({"status": "ok", "detail": "returned " + _short(outcome)})
        except Hung:
            results.append({"status": "hung", "detail": "Still running after 2 seconds"})
        except BaseException as exc:  # noqa: BLE001 - SystemExit and friends count as crashes too
            signal.alarm(0)
            frames = traceback.extract_tb(exc.__traceback__)
            last = frames[-1] if frames else None
            deliberate = bool(
                last
                and os.path.realpath(last.filename) == real_module
                and (last.line or "").strip().startswith("raise")
            )
            results.append(
                {
                    "status": "rejected" if deliberate else "crashed",
                    "detail": f"{type(exc).__name__}: {str(exc)[:110]}",
                }
            )
        finally:
            signal.alarm(0)
    print(MARKER + json.dumps({"results": results}))


if __name__ == "__main__":
    main()
