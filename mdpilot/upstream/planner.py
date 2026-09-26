"""Reads the upstream longitudinal planner's collision warning and the following time of a personality."""
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import get_T_FOLLOW
from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner

__all__ = ["LongitudinalPlanner", "fcw", "follow_time"]


def fcw(planner) -> bool:
  return bool(planner.fcw)


def follow_time(personality) -> float:
  return float(get_T_FOLLOW(personality))
