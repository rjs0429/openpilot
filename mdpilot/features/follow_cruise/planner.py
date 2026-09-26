"""Lead following for a stock cruise that openpilot can only steer through its buttons.

The cruise slows the car only by closing the throttle, a few tenths of m/s^2 that depend on speed and grade.
The target speed is therefore the fastest the car may close in on the lead while a share of that coasting
still brings it down to the lead's speed at the following distance: the set speed is trimmed down to it, and
once the lead needs most of what coasting gives, the cruise is canceled into a coast. The upstream plan is
still solved alongside for its collision warning.
"""
import math
from dataclasses import dataclass

from openpilot.mdpilot.features.follow_cruise.coast import coast_decel
from openpilot.mdpilot.upstream import DT_MDL, lead_present
from openpilot.mdpilot.upstream import planner as upstream_planner

# Buttons, the ECM and the throttle take about this long to answer.
ACTUATOR_DELAY = 1.0
STOP_GAP_M = 6.

# Shares of the coasting deceleration: the set speed is trimmed to ask for at most TRIM_SHARE of it, a coast
# starts once the lead needs COAST_SHARE and ends once it needs no more than RELEASE_SHARE.
TRIM_SHARE = 0.35
COAST_SHARE = 0.7
RELEASE_SHARE = 0.2
# Closing slower than this is trimmed away by the set speed, never coasted.
COAST_MIN_CLOSING = 1.4
# Inside the following distance the target falls below the lead's speed by this much per metre.
GAP_RECOVERY = 0.1
TARGET_RISE_TAU = 2.0
ACCEL_TAU = 2.0
ACCEL_MAX = 0.5

COAST_ENTER_TIME = 0.5
COAST_EXIT_TIME = 0.3
COAST_MIN_DWELL = 1.5
# Coasting on past the lead's own speed only loses ground.
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
  a_needed: float = 0.
  follow_gap: float = 0.


def required_decel(v_ego: float, d_rel: float, v_lead: float) -> float:
  """Mean deceleration needed to fall back to the lead's speed without closing inside the minimum gap."""
  dv = v_ego - v_lead
  if dv <= 0.:
    return 0.
  budget = d_rel - (MIN_GAP_M + MIN_GAP_T * v_lead) - dv * REACTION_T
  if budget <= 0.:
    return math.inf
  return dv ** 2 / (2. * budget)


def following_gap(v_lead: float, t_follow: float) -> float:
  return STOP_GAP_M + t_follow * v_lead


def closing_room(v_ego: float, d_rel: float, v_lead: float, gap: float) -> float:
  """Distance left for falling back to the lead's speed before the following gap, once the actuators answer."""
  return d_rel - gap - max(0., v_ego - v_lead) * ACTUATOR_DELAY


def needed_decel(v_ego: float, v_lead: float, room: float) -> float:
  dv = v_ego - v_lead
  if dv <= 0.:
    return 0.
  if room <= 0.:
    return math.inf
  return dv ** 2 / (2. * room)


def envelope_speed(v_lead: float, room: float, decel: float) -> float:
  """Fastest speed from which decelerating at `decel` gets down to the lead's speed within `room`."""
  if room >= 0.:
    return v_lead + math.sqrt(2. * decel * room)
  return max(0., v_lead + GAP_RECOVERY * room)


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
    self._v_target: float | None = None

  def reset(self) -> None:
    self.lead = LeadFilter()
    self._coast = False
    self._coast_timer = 0.
    self._coast_dwell = COAST_MIN_DWELL
    self._decel_timer = 0.
    self._collision_hold = 0.
    self._v_target = None

  def update(self, sm, planner, dt: float = DT_MDL) -> FollowOutput:
    CS = sm['carState']
    v_cruise = CS.cruiseState.speed
    self._update_grade(sm['carControl'], dt)
    if v_cruise <= 0.:
      self.reset()
      self.out = FollowOutput(grade=self.grade_pct)
      return self.out

    v_ego = CS.vEgo
    lead_msg = sm['radarState'].leadOne
    self.lead.update(lead_msg, v_ego, dt)
    lead = self.lead.present
    a_coast = coast_decel(v_ego, self.grade_pct)

    gap = following_gap(self.lead.v_lead, upstream_planner.follow_time(sm['selfdriveState'].personality)) if lead else 0.
    room = closing_room(v_ego, self.lead.d_rel, self.lead.v_lead, gap) if lead else math.inf
    a_needed = needed_decel(v_ego, self.lead.v_lead, room) if lead else 0.

    v_goal = v_cruise
    if lead:
      v_goal = min(v_goal, envelope_speed(self.lead.v_lead, room, TRIM_SHARE * a_coast))
      if not lead_present(lead_msg) and self._v_target is not None:
        v_goal = min(v_goal, self._v_target)
    lead_limited = v_goal < v_cruise
    if self._v_target is None or v_goal < self._v_target:
      self._v_target = v_goal
    else:
      self._v_target = _lowpass(self._v_target, v_goal, TARGET_RISE_TAU, dt)
    v_target = self._v_target
    a_target = max(-a_coast, min(ACCEL_MAX, (v_target - v_ego) / ACCEL_TAU))

    a_required = required_decel(v_ego, self.lead.d_rel, self.lead.v_lead) if lead else 0.
    self._decel_timer = self._decel_timer + dt if a_required > max(a_coast, ALERT_MIN_DECEL) else 0.
    over_coast = self._decel_timer >= ALERT_DECEL_TIME - 1e-6
    closing = self.lead.present and v_ego > self.lead.v_lead
    ttc = self.lead.d_rel / (v_ego - self.lead.v_lead) if closing else math.inf
    collision = (closing and lead_present(lead_msg) and self.lead.prob >= COLLISION_PROB and
                 (ttc < COLLISION_TTC or self.lead.d_rel < COLLISION_HEADWAY * v_ego))
    fcw = upstream_planner.fcw(planner)
    self._collision_hold = COLLISION_HOLD if (collision or fcw) else max(0., self._collision_hold - dt)
    alert_level = 2 if self._collision_hold > 0. else (1 if over_coast else 0)

    self._update_coast(lead, a_needed / a_coast, v_ego, alert_level > 0, dt)

    self.out = FollowOutput(
      active=True, v_cruise=v_cruise, v_target=v_target, a_target=a_target, coast_request=self._coast,
      alert_level=alert_level, lead_limited=lead_limited, lead_valid=lead, d_rel=self.lead.d_rel,
      v_lead=self.lead.v_lead, a_required=min(a_required, 10.), a_coast_limit=a_coast, grade=self.grade_pct, fcw=fcw,
      a_needed=min(a_needed, 10.), follow_gap=gap,
    )
    return self.out

  def _update_coast(self, lead: bool, share: float, v_ego: float, alerting: bool, dt: float) -> None:
    self._coast_dwell += dt
    caught = not lead or v_ego <= self.lead.v_lead + COAST_LEAD_MARGIN
    if not self._coast:
      if alerting and lead:
        self._set_coast(True)
        return
      want = lead and v_ego - self.lead.v_lead >= COAST_MIN_CLOSING and share >= COAST_SHARE
      self._coast_timer = self._coast_timer + dt if want else 0.
      if self._coast_timer >= COAST_ENTER_TIME - 1e-6 and self._coast_dwell >= COAST_MIN_DWELL:
        self._set_coast(True)
    else:
      release = (caught or share <= RELEASE_SHARE) and not alerting
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
