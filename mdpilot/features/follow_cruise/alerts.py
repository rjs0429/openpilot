"""Runs inside selfdrived: gap assist alerts.

All alerts are permanent so they show whether or not steering is engaged. The collision alert reuses the
upstream forward collision warning; the others mirror the steering saturation prompt. Gap assist never speeds the
car up itself, so when the plan wants more speed the driver is asked, quietly and once, to use the pedal.
"""
from openpilot.mdpilot import manifest
from openpilot.mdpilot.features.follow_cruise.mode import GAP_ASSIST, cruise_mode
from openpilot.mdpilot.upstream import DT_CTRL, Params, messaging
from openpilot.mdpilot.upstream.alerts import AlertSize, AlertStatus, AudibleAlert, EventName, Priority, VisualAlert, is_mici, \
                                               permanent_alert

ALERT_DECEL_LIMIT = 1
ALERT_COLLISION = 2
PLAN_LOST_TIME = 1.0
ACCEL_PROMPT_TIME = 4.0
# The prompt comes back only after the plan has stopped asking for this long.
ACCEL_REARM_TIME = 5.0


def _prompt(name: str, text: tuple[str, str], mici_text: tuple[str, str]):
  return permanent_alert(name, mici_text if is_mici() else text, AlertStatus.userPrompt, AlertSize.mid, Priority.MID,
                         VisualAlert.none, AudibleAlert.promptRepeat, 2.)


class FollowAlerts:
  @classmethod
  def create(cls, CP, params=None):
    if not (manifest.enabled("follow_cruise") and CP.brand == manifest.BRAND):
      return None
    return cls() if cruise_mode(params if params is not None else Params()) == GAP_ASSIST else None

  def __init__(self):
    self.sm = messaging.SubMaster(['followPlanMD'])
    self.alert_level = 0
    self.plan_lost_frames = 0
    self.accel_frames = 0
    self.accel_quiet_frames = 0
    self.accel_armed = True
    self.decel_limit_alert = _prompt("followDecelLimit", ("Take Control", "Cruise Cannot Slow Down Enough"),
                                     ("take control", "cruise can't slow enough"))
    self.plan_lost_alert = _prompt("followUnavailable", ("Take Control", "Gap Assist Unavailable"),
                                   ("take control", "gap assist unavailable"))
    self.accel_alert = permanent_alert("followAccelPrompt",
                                       ("speed up with the gas", "release to keep the speed") if is_mici() else
                                       ("Speed Up With the Gas Pedal", "Release It to Keep the Speed"),
                                       AlertStatus.normal, AlertSize.mid, Priority.LOW, VisualAlert.none,
                                       AudibleAlert.none, 0.)

  def update_events(self, events, CS) -> None:
    self.sm.update(0)
    plan = self.sm['followPlanMD']
    fresh = self.sm.alive['followPlanMD'] and self.sm.valid['followPlanMD'] and plan.active
    self.alert_level = plan.alertLevel if fresh else 0
    following = CS.cruiseState.speed > 0.
    self.plan_lost_frames = self.plan_lost_frames + 1 if following and not fresh else 0
    if self.alert_level >= ALERT_COLLISION:
      events.add(EventName.fcw)
    self._update_accel_prompt(fresh and plan.accelRequest)

  def _update_accel_prompt(self, asked: bool) -> None:
    if asked:
      self.accel_quiet_frames = 0
      self.accel_frames = self.accel_frames + 1 if self.accel_armed else 0
      if self.accel_frames * DT_CTRL >= ACCEL_PROMPT_TIME:
        self.accel_armed = False
    else:
      self.accel_frames = 0
      self.accel_quiet_frames += 1
      if self.accel_quiet_frames * DT_CTRL >= ACCEL_REARM_TIME:
        self.accel_armed = True

  def alerts(self) -> list:
    if self.plan_lost_frames * DT_CTRL >= PLAN_LOST_TIME:
      return [self.plan_lost_alert]
    if self.alert_level == ALERT_DECEL_LIMIT:
      return [self.decel_limit_alert]
    return [self.accel_alert] if self.accel_frames > 0 else []
