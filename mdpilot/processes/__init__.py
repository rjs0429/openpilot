"""Attaches the fork to upstream processes by name: each upstream entry is replaced by a copy with only its module
swapped, so its start conditions stay upstream's."""
import copy
import importlib

from openpilot.mdpilot import manifest

# upstream process -> (fork entry module, features it carries)
OVERRIDES = {
  "card": ("openpilot.mdpilot.processes.card", ("follow_cruise",)),
  "plannerd": ("openpilot.mdpilot.processes.plannerd", ("follow_cruise",)),
  "selfdrived": ("openpilot.mdpilot.processes.selfdrived", ("follow_cruise", "forward_watch")),
  "torqued": ("openpilot.mdpilot.processes.torqued", ("torque_learning",)),
  "hardwared": ("openpilot.mdpilot.processes.hardwared", ("power",)),
}
FORWARDWATCHD = "openpilot.mdpilot.processes.forwardwatchd"


def iscar(started: bool, params, CP) -> bool:
  return started and not CP.notCar


def _fail(feature: str) -> None:
  from openpilot.mdpilot.hooks import report
  manifest.switch_off(feature)
  report(feature, "process_config")


def _check(p, entry) -> None:
  from openpilot.system.manager.process import PythonProcess
  if not isinstance(p, PythonProcess):
    raise TypeError(f"{p.name} is no longer a PythonProcess")
  importlib.import_module(entry[0])


def new_processes() -> list:
  from openpilot.system.manager.process import PythonProcess
  procs = []
  if manifest.enabled("forward_watch"):
    try:
      importlib.import_module(FORWARDWATCHD)
      procs.append(PythonProcess("forwardwatchd", FORWARDWATCHD, iscar))
    except Exception:
      _fail("forward_watch")
  return procs


def apply(procs: list) -> list:
  # A feature whose process entry is missing or cannot be set up is switched off in every process.
  by_name = {p.name: p for p in procs}
  for name, entry in OVERRIDES.items():
    if not any(manifest.enabled(f) for f in entry[1]):
      continue
    try:
      if name not in by_name:
        raise KeyError(f"upstream has no {name} process")
      _check(by_name[name], entry)
    except Exception:
      for feature in entry[1]:
        _fail(feature)

  out = []
  for p in procs:
    entry = OVERRIDES.get(p.name)
    if entry is not None and any(manifest.enabled(f) for f in entry[1]):
      stock_module = p.module
      p = copy.copy(p)
      p.module = entry[0]
      p.stock_module = stock_module
    out.append(p)
  return out + new_processes()
