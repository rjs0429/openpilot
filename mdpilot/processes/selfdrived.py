UPSTREAM = "openpilot.selfdrive.selfdrived.selfdrived"

FEATURES = ("follow_cruise", "forward_watch")


def attach(selfdrived) -> None:
  from openpilot.mdpilot.processes.selfdrived_md import build
  selfdrived.SelfdriveD = build(selfdrived.SelfdriveD)


def main() -> None:
  from openpilot.mdpilot.hooks import run_process
  run_process(UPSTREAM, attach, FEATURES)
