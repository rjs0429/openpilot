UPSTREAM = "openpilot.system.hardware.hardwared"
POWER_MONITORING = "openpilot.system.hardware.power_monitoring"

FEATURES = ("power",)


def attach(hardwared) -> None:
  import importlib
  from openpilot.mdpilot.features.power.constants import OVERRIDES
  power_monitoring = importlib.import_module(POWER_MONITORING)
  missing = [name for name in OVERRIDES if not hasattr(power_monitoring, name)]
  if missing:
    raise AttributeError(f"power_monitoring no longer defines {missing}")
  for name, value in OVERRIDES.items():
    setattr(power_monitoring, name, value)


def main() -> None:
  from openpilot.mdpilot.hooks import run_process
  run_process(UPSTREAM, attach, FEATURES)
