"""The fork's window onto upstream: features and ui import upstream only through this package.

When upstream moves or renames something, fix it here. tests/test_contract.py lists what the fork expects.
"""
import cereal.messaging as messaging
from cereal import car, custom, log
from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.common.realtime import DT_CTRL, DT_MDL, Priority, config_realtime_process
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.car.cruise import V_CRUISE_UNSET

__all__ = ["messaging", "car", "custom", "log", "CV", "Params", "DT_CTRL", "DT_MDL", "Priority", "config_realtime_process",
           "cloudlog", "V_CRUISE_UNSET", "lead_present"]


def lead_present(lead) -> bool:
  """Whether a radarState lead is valid."""
  return bool(lead.status)
