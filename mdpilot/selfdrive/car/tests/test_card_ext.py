import time

import cereal.messaging as messaging
from cereal import car
from openpilot.mdpilot.selfdrive.car.card_ext import MIN_PLAN_SPEED, PLAN_TIMEOUT, CardExt
from openpilot.selfdrive.car.cruise import V_CRUISE_UNSET


class FakeSubMaster:
  def __init__(self, plan=None, age=0., valid=True):
    msg = messaging.new_message('followPlanMD')
    if plan is not None:
      for k, v in plan.items():
        setattr(msg.followPlanMD, k, v)
    self.data = {'followPlanMD': msg.followPlanMD.as_reader()}
    self.seen = {'followPlanMD': plan is not None}
    self.valid = {'followPlanMD': valid}
    self.recv_time = {'followPlanMD': time.monotonic() - age}

  def update(self, timeout=0):
    pass

  def __getitem__(self, s):
    return self.data[s]


def make_ext(brand='avante_md', sm=None):
  CP = car.CarParams.new_message()
  CP.brand = brand
  ext = CardExt(CP.as_reader())
  if sm is not None:
    ext.sm = sm
  return ext


def carcontrol():
  CC = car.CarControl.new_message()
  CC.actuators.torque = 0.3
  return CC.as_reader()


PLAN = {'active': True, 'vTarget': 20., 'aTarget': -0.4, 'coastRequest': True}


class TestCardExt:
  def test_other_brands_untouched(self):
    ext = make_ext('toyota')
    CC = carcontrol()
    assert ext.update_car_control(CC) is CC
    assert ext.sm is None

  def test_fresh_plan_is_injected(self):
    CC = make_ext(sm=FakeSubMaster(PLAN)).update_car_control(carcontrol())
    assert CC.actuators.speed == 20.
    assert abs(CC.actuators.accel + 0.4) < 1e-6
    assert CC.cruiseControl.cancel
    assert abs(CC.actuators.torque - 0.3) < 1e-6

  def test_stopped_target_still_counts_as_a_plan(self):
    CC = make_ext(sm=FakeSubMaster({**PLAN, 'vTarget': 0.})).update_car_control(carcontrol())
    assert abs(CC.actuators.speed - MIN_PLAN_SPEED) < 1e-6

  def test_no_plan_when_stale_invalid_or_inactive(self):
    for sm in (FakeSubMaster(PLAN, age=PLAN_TIMEOUT + 0.1), FakeSubMaster(PLAN, valid=False),
               FakeSubMaster({**PLAN, 'active': False}), FakeSubMaster(None)):
      CC = make_ext(sm=sm).update_car_control(carcontrol())
      assert CC.actuators.speed == 0.
      assert not CC.cruiseControl.cancel

  def test_set_speed_shown_while_following(self):
    ext = make_ext(sm=FakeSubMaster())
    CS = car.CarState.new_message()
    CS.vCruise = 40.
    CS.vCruiseCluster = 40.
    ext.update_car_state(CS)
    assert CS.vCruise == 40.
    assert CS.vCruiseCluster == V_CRUISE_UNSET

    CS.cruiseState.speed = 25.
    CS.cruiseState.speedCluster = 25.5
    ext.update_car_state(CS)
    assert abs(CS.vCruise - 90.) < 1e-3
    assert abs(CS.vCruiseCluster - 91.8) < 1e-3
