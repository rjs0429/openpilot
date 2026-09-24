UPSTREAM = "openpilot.selfdrive.car.card"

FEATURES = ("follow_cruise",)


def attach(card) -> None:
  from openpilot.mdpilot.processes.card_md import build
  card.Car = build(card.Car)


def main() -> None:
  from openpilot.mdpilot.hooks import run_process
  run_process(UPSTREAM, attach, FEATURES)
