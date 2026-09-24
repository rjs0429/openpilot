"""Runs inside card: hands the latest follow plan to the car controller and shows the follow set speed.

Follow cruise runs only while every process carrying it is healthy: once any of them reports it switched off,
no more commands are sent, so the car never follows without its alerts.
"""
import time

from opendbc.car.avante_md.follow.command import FollowCommand
from openpilot.mdpilot import manifest
from openpilot.mdpilot.runtime.health import read_status
from openpilot.mdpilot.upstream import CV, DT_MDL, V_CRUISE_UNSET, Params, messaging

PLAN_TIMEOUT = 3 * DT_MDL
MIN_PLAN_SPEED = 0.1
# The plan arrives at model rate; polling on every control cycle costs more than it gains.
POLL_EVERY = 5
STATUS_EVERY = 100  # control frames


class FollowCard:
  @classmethod
  def create(cls, CP):
    return cls() if manifest.enabled("follow_cruise") and CP.brand == manifest.BRAND else None

  def __init__(self, params=None):
    self.sm = messaging.SubMaster(['followPlanMD'])
    self.params = params if params is not None else Params()
    self.frame = 0
    self.switched_off = False

  def update_car_state(self, CS) -> None:
    if CS.cruiseState.speed > 0.:
      CS.vCruise = float(CS.cruiseState.speed * CV.MS_TO_KPH)
      CS.vCruiseCluster = float(CS.cruiseState.speedCluster * CV.MS_TO_KPH)
    else:
      CS.vCruiseCluster = float(V_CRUISE_UNSET)

  def command(self) -> FollowCommand | None:
    if self.frame % STATUS_EVERY == 0 and not self.switched_off:
      self.switched_off = "follow_cruise" in read_status(self.params)
    self.frame += 1
    if self.frame % POLL_EVERY == 0:
      self.sm.update(0)
    if self.switched_off:
      return None
    plan = self.sm['followPlanMD']
    recent = self.sm.seen['followPlanMD'] and time.monotonic() - self.sm.recv_time['followPlanMD'] <= PLAN_TIMEOUT
    if not (recent and self.sm.valid['followPlanMD'] and plan.active):
      return None
    return FollowCommand(max(plan.vTarget, MIN_PLAN_SPEED), plan.aTarget, plan.coastRequest)

  def push_command(self, CI) -> None:
    CI.CC.set_follow_command(self.command())
