UPSTREAM = "openpilot.selfdrive.controls.plannerd"

FEATURES = ("follow_cruise",)


def attach(plannerd) -> None:
  from openpilot.mdpilot.processes.plannerd_md import build
  plannerd.LongitudinalPlanner = build(plannerd.LongitudinalPlanner)


def main() -> None:
  from openpilot.mdpilot.hooks import run_process
  run_process(UPSTREAM, attach, FEATURES)
