UPSTREAM = "openpilot.selfdrive.locationd.torqued"

FEATURES = ("torque_learning",)


def attach(torqued) -> None:
  from openpilot.mdpilot.features.torque_learning import BRANDS
  for brand in BRANDS:
    if brand not in torqued.ALLOWED_CARS:
      torqued.ALLOWED_CARS.append(brand)


def main() -> None:
  from openpilot.mdpilot.hooks import run_process
  run_process(UPSTREAM, attach, FEATURES)
