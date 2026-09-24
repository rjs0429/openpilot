"""Reads the upstream longitudinal planner's solved trajectory."""
from openpilot.selfdrive.controls.lib.drive_helpers import get_accel_from_plan
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalPlanSource
from openpilot.selfdrive.controls.lib.longitudinal_planner import CONTROL_N_T_IDX, LongitudinalPlanner

LEAD_SOURCES = (LongitudinalPlanSource.lead0, LongitudinalPlanSource.lead1)

__all__ = ["LongitudinalPlanner", "final_speed", "accel_at", "lead_limited", "fcw", "v_ego_stopping"]


def final_speed(planner) -> float:
  return float(planner.v_desired_trajectory[-1])


def accel_at(planner, action_t: float, v_ego_stopping: float) -> float:
  return float(get_accel_from_plan(planner.v_desired_trajectory, planner.a_desired_trajectory, CONTROL_N_T_IDX,
                                   action_t=action_t, vEgoStopping=v_ego_stopping)[0])


def lead_limited(planner) -> bool:
  return planner.mpc.source in LEAD_SOURCES


def fcw(planner) -> bool:
  return bool(planner.fcw)


def v_ego_stopping(CP) -> float:
  return CP.vEgoStopping
