"""How hard the Avante MD slows with the throttle closed, as positive deceleration in m/s^2.

The stock cruise has no brake authority: canceling it leaves engine braking and road load, which grow with
speed and depend strongly on grade.
"""
import numpy as np

from openpilot.mdpilot.upstream import CV

COAST_BP_KPH = [40., 50., 60., 70., 80., 90., 100., 110., 120.]
# Conservative flat-road coasting deceleration, what canceling the cruise can be counted on for.
COAST_DECEL = [0.22, 0.24, 0.25, 0.28, 0.32, 0.34, 0.37, 0.42, 0.44]

GRADE_UPHILL_PER_PCT = 0.080
GRADE_DOWNHILL_PER_PCT = 0.098
MARGIN = 0.05
MIN_DECEL = 0.05


def grade_decel(grade_pct: float) -> float:
  return grade_pct * (GRADE_UPHILL_PER_PCT if grade_pct > 0. else GRADE_DOWNHILL_PER_PCT)


def coast_decel(v_ego: float, grade_pct: float) -> float:
  base = float(np.interp(v_ego * CV.MS_TO_KPH, COAST_BP_KPH, COAST_DECEL))
  return max(MIN_DECEL, base + grade_decel(grade_pct) - MARGIN)
