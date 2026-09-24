"""The only fork module upstream files import.

The manager imports every process module before starting anything, so this file imports nothing but the
standard library. A failure to attach the fork leaves the upstream behavior unchanged and is reported. Upstream
names used outside a guard (a process entry's UPSTREAM path, the swapped classes' attributes listed in
upstream/contract.py) fail the process if upstream changes them; tests/test_contract.py catches that first.
"""
import importlib
import traceback


def report(feature: str, where: str) -> None:
  try:
    from openpilot.mdpilot.runtime.health import report_failure
    report_failure(feature, where)
  except Exception:
    traceback.print_exc()


def apply_processes(procs: list) -> list:
  try:
    return importlib.import_module("openpilot.mdpilot.processes").apply(procs)
  except Exception:
    report("processes", "process_config")
    return procs


def run_process(upstream_module: str, attach, features: tuple[str, ...]) -> None:
  """Runs an upstream process with the fork attached, or unmodified when attaching fails."""
  upstream = importlib.import_module(upstream_module)
  try:
    attach(upstream)
  except Exception:
    for feature in features:
      report(feature, upstream_module)
  upstream.main()


class LateralGate:
  """controlsd hook: may withhold lateral control. Allows everything when the gate is off or broken."""

  def __init__(self, CP):
    self._gate = None
    try:
      from openpilot.mdpilot.features.lateral_gate.gate import create
      self._gate = create(CP)
    except Exception:
      report("lateral_gate", "controlsd")

  def allowed(self, CS, model_v2) -> bool:
    if self._gate is None:
      return True
    try:
      return self._gate.allowed(CS, model_v2)
    except Exception:
      self._gate = None
      report("lateral_gate", "controlsd")
      return True


def extend_toggles(layout) -> None:
  try:
    importlib.import_module("openpilot.mdpilot.ui.toggles").extend(layout)
  except Exception:
    report("ui", "toggles")
