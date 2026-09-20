"""card hooks: hand the follow plan to the car port and show the follow set speed.

The plan rides in CarControl fields that stock-cruise cars leave unused: actuators.speed (target speed, 0 when
there is no plan), actuators.accel and cruiseControl.cancel (request to coast).
"""
import time

import cereal.messaging as messaging
from openpilot.common.constants import CV
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.car.cruise import V_CRUISE_UNSET

PLAN_TIMEOUT = 3 * DT_MDL
MIN_PLAN_SPEED = 0.1


class CardExt:
  def __init__(self, CP):
    self.enabled = CP.brand == 'avante_md'
    self.sm = messaging.SubMaster(['followPlanMD']) if self.enabled else None

  def update_car_state(self, CS) -> None:
    if not self.enabled:
      return
    if CS.cruiseState.speed > 0.:
      CS.vCruise = float(CS.cruiseState.speed * CV.MS_TO_KPH)
      CS.vCruiseCluster = float(CS.cruiseState.speedCluster * CV.MS_TO_KPH)
    else:
      CS.vCruiseCluster = float(V_CRUISE_UNSET)

  def update_car_control(self, CC):
    if not self.enabled:
      return CC

    self.sm.update(0)
    plan = self.sm['followPlanMD']
    recent = self.sm.seen['followPlanMD'] and time.monotonic() - self.sm.recv_time['followPlanMD'] <= PLAN_TIMEOUT
    if not (recent and self.sm.valid['followPlanMD'] and plan.active):
      return CC

    cc = CC.as_builder()
    cc.actuators.speed = max(plan.vTarget, MIN_PLAN_SPEED)
    cc.actuators.accel = plan.aTarget
    cc.cruiseControl.cancel = plan.coastRequest
    return cc.as_reader()
