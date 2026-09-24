"""Lead following for a stock cruise that openpilot can only steer through its buttons.

This reads the upstream longitudinal plan, which already targets the driver's set speed because card
reports it as the cruise speed, and decides from it when to cancel into a coast and when coasting will not
be enough. Buttons reach the ECM far slower than a throttle would, so the acceleration is taken further
along the planned trajectory than upstream takes it.
"""
import math
from dataclasses import dataclass

from openpilot.mdpilot.features.follow_cruise.coast import coast_decel
from openpilot.mdpilot.upstream import DT_MDL, lead_present
from openpilot.mdpilot.upstream import planner as upstream_planner

ACTUATOR_DELAY = 1.0

COAST_ENTER_ACCEL = -0.40
COAST_EXIT_ACCEL = -0.03
COAST_ENTER_TIME = 0.5
COAST_EXIT_TIME = 0.3
COAST_MIN_DWELL = 1.5
# Speed still to shed for the lead. Below this the set speed can trim it away without dropping the cruise.
COAST_ENTER_DEFICIT = 2.2
# Coasting on past the lead's own speed only loses ground, whatever the plan still asks for.
COAST_LEAD_MARGIN = 0.5

LEAD_NEAR_M = 50.
LEAD_ENTER_PROB = (0.5, 0.9)  # near, far
LEAD_ENTER_TIME = (0.25, 1.0)
LEAD_EXIT_TIME = (1.5, 3.0)
LEAD_D_TAU = 0.25
LEAD_V_TAU = 0.5

GRADE_TAU = 1.0
GRADE_MAX_PCT = 8.

MIN_GAP_M = 5.
MIN_GAP_T = 0.6
REACTION_T = 1.0
ALERT_DECEL_TIME = 0.5
# Below this the lead closes in too slowly to be worth a prompt, even where coasting cannot slow the car.
ALERT_MIN_DECEL = 0.15
COLLISION_HOLD = 1.0
COLLISION_TTC = 2.5
COLLISION_HEADWAY = 0.4
COLLISION_PROB = 0.9


def _lowpass(x: float, target: float, tau: float, dt: float) -> float:
  return x + min(1., dt / tau) * (target - x)


class LeadFilter:
  """A vision lead that has to be seen for a while before it counts and missed for a while before it is gone."""

  def __init__(self):
    self.present = False
    self.d_rel = 0.
    self.v_lead = 0.
    self.prob = 0.
    self._enter = 0.
    self._lost = 0.
    self._restart = True

  def update(self, lead, v_ego: float, dt: float) -> None:
    raw = lead_present(lead)
    if not raw and self.present:
      self.d_rel = max(0., self.d_rel - (v_ego - self.v_lead) * dt)
    if raw:
      if self._restart:
        self.d_rel, self.v_lead = lead.dRel, lead.vLead
        self._restart = False
      else:
        self.d_rel = _lowpass(self.d_rel, lead.dRel, LEAD_D_TAU, dt)
        self.v_lead = _lowpass(self.v_lead, lead.vLead, LEAD_V_TAU, dt)
      self.prob = lead.modelProb
    far = 0 if self.d_rel < LEAD_NEAR_M else 1

    if not self.present:
      confident = raw and lead.modelProb >= LEAD_ENTER_PROB[far]
      self._enter = self._enter + dt if confident else 0.
      if self._enter >= LEAD_ENTER_TIME[far] - 1e-6:
        self.present = True
        self._lost = 0.
      elif not raw:
        self._restart = True
    else:
      self._lost = 0. if raw else self._lost + dt
      if self._lost >= LEAD_EXIT_TIME[far] - 1e-6:
        self.present = False
        self._enter = 0.
        self._restart = True


@dataclass
class FollowOutput:
  active: bool = False
  v_cruise: float = 0.
  v_target: float = 0.
  a_target: float = 0.
  coast_request: bool = False
  alert_level: int = 0
  lead_limited: bool = False
  lead_valid: bool = False
  d_rel: float = 0.
  v_lead: float = 0.
  a_required: float = 0.
  a_coast_limit: float = 0.
  grade: float = 0.
  fcw: bool = False


def required_decel(v_ego: float, d_rel: float, v_lead: float) -> float:
  """Mean deceleration needed to fall back to the lead's speed without closing inside the minimum gap."""
  dv = v_ego - v_lead
  if dv <= 0.:
    return 0.
  budget = d_rel - (MIN_GAP_M + MIN_GAP_T * v_lead) - dv * REACTION_T
  if budget <= 0.:
    return math.inf
  return dv ** 2 / (2. * budget)


class FollowPlanner:
  def __init__(self, CP):
    self.CP = CP
    self.lead = LeadFilter()
    self.out = FollowOutput()
    self.grade_pct = 0.
    self._grade_init = False
    self._coast = False
    self._coast_timer = 0.
    self._coast_dwell = COAST_MIN_DWELL
    self._decel_timer = 0.
    self._collision_hold = 0.
    self._v_target_prev = 0.

  def reset(self) -> None:
    self.lead = LeadFilter()
    self._coast = False
    self._coast_timer = 0.
    self._coast_dwell = COAST_MIN_DWELL
    self._decel_timer = 0.
    self._collision_hold = 0.
    self._v_target_prev = 0.

  def update(self, sm, planner, dt: float = DT_MDL) -> FollowOutput:
    CS = sm['carState']
    v_cruise = CS.cruiseState.speed
    self._update_grade(sm['carControl'], dt)
    if v_cruise <= 0.:
      self.reset()
      self.out = FollowOutput(grade=self.grade_pct)
      return self.out

    lead_msg = sm['radarState'].leadOne
    self.lead.update(lead_msg, CS.vEgo, dt)

    v_target = min(max(upstream_planner.final_speed(planner), 0.), v_cruise)
    a_target = upstream_planner.accel_at(planner, ACTUATOR_DELAY, upstream_planner.v_ego_stopping(self.CP))
    lead_limited = upstream_planner.lead_limited(planner)
    if self.lead.present and not lead_present(lead_msg):
      v_target = min(v_target, self._v_target_prev)
      a_target = min(a_target, 0.)
      lead_limited = True
    self._v_target_prev = v_target

    v_ego = CS.vEgo
    a_coast = coast_decel(v_ego, self.grade_pct)
    a_required = required_decel(v_ego, self.lead.d_rel, self.lead.v_lead) if self.lead.present else 0.

    self._decel_timer = self._decel_timer + dt if a_required > max(a_coast, ALERT_MIN_DECEL) else 0.
    over_coast = self._decel_timer >= ALERT_DECEL_TIME - 1e-6
    closing = self.lead.present and v_ego > self.lead.v_lead
    ttc = self.lead.d_rel / (v_ego - self.lead.v_lead) if closing else math.inf
    collision = (closing and lead_present(lead_msg) and self.lead.prob >= COLLISION_PROB and
                 (ttc < COLLISION_TTC or self.lead.d_rel < COLLISION_HEADWAY * v_ego))
    fcw = upstream_planner.fcw(planner)
    self._collision_hold = COLLISION_HOLD if (collision or fcw) else max(0., self._collision_hold - dt)
    alert_level = 2 if self._collision_hold > 0. else (1 if over_coast else 0)

    self._update_coast(a_target, lead_limited, alert_level > 0, v_ego, v_target, dt)

    self.out = FollowOutput(
      active=True, v_cruise=v_cruise, v_target=v_target, a_target=a_target, coast_request=self._coast,
      alert_level=alert_level, lead_limited=lead_limited, lead_valid=self.lead.present, d_rel=self.lead.d_rel,
      v_lead=self.lead.v_lead, a_required=min(a_required, 10.), a_coast_limit=a_coast, grade=self.grade_pct, fcw=fcw,
    )
    return self.out

  def _update_coast(self, a_target: float, lead_limited: bool, alerting: bool, v_ego: float, v_target: float,
                    dt: float) -> None:
    self._coast_dwell += dt
    caught = v_ego <= v_target or (self.lead.present and v_ego <= self.lead.v_lead + COAST_LEAD_MARGIN)
    if not self._coast:
      if alerting and lead_limited:
        self._set_coast(True)
        return
      want = (lead_limited and not caught and
              (a_target < COAST_ENTER_ACCEL or v_ego - v_target > COAST_ENTER_DEFICIT))
      self._coast_timer = self._coast_timer + dt if want else 0.
      if self._coast_timer >= COAST_ENTER_TIME - 1e-6 and self._coast_dwell >= COAST_MIN_DWELL:
        self._set_coast(True)
    else:
      release = (a_target > COAST_EXIT_ACCEL or caught or not lead_limited) and not alerting
      self._coast_timer = self._coast_timer + dt if release else 0.
      if self._coast_timer >= COAST_EXIT_TIME - 1e-6 and self._coast_dwell >= COAST_MIN_DWELL:
        self._set_coast(False)

  def _set_coast(self, coast: bool) -> None:
    self._coast = coast
    self._coast_timer = 0.
    self._coast_dwell = 0.

  def _update_grade(self, CC, dt: float) -> None:
    if len(CC.orientationNED) != 3:
      return
    raw = max(-GRADE_MAX_PCT, min(GRADE_MAX_PCT, math.tan(CC.orientationNED[1]) * 100.))
    if not self._grade_init:
      self.grade_pct = raw
      self._grade_init = True
    else:
      self.grade_pct = _lowpass(self.grade_pct, raw, GRADE_TAU, dt)
