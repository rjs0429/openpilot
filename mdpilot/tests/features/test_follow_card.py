import time
import unittest  # noqa: TID251

import cereal.messaging as messaging
from cereal import car
from opendbc.car.avante_md.follow.command import FollowCommand
from openpilot.mdpilot.features.follow_cruise.card import MIN_PLAN_SPEED, PLAN_TIMEOUT, FollowCard
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


def car_params(brand='avante_md'):
  CP = car.CarParams.new_message()
  CP.brand = brand
  return CP.as_reader()


class NoStatusParams:
  def get(self, key):
    return None


def make_card(sm, CI=None):
  card = FollowCard.create(car_params(), CI)
  card.sm = sm
  card.params = NoStatusParams()
  return card


class FakeController:
  def __init__(self):
    self.cmd = 'unset'
    self.cruise_enabled = None
    self.display: float | None = None

  def set_follow_command(self, cmd):
    self.cmd = cmd

  def set_cruise_enabled(self, enabled):
    self.cruise_enabled = enabled

  def cruise_display_kph(self):
    return self.display


class FakeInterface:
  def __init__(self):
    self.CC = FakeController()


PLAN = {'active': True, 'vTarget': 20., 'aTarget': -0.4, 'coastRequest': True}


class TestFollowCard(unittest.TestCase):
  def test_other_brands_get_nothing(self):
    self.assertIsNone(FollowCard.create(car_params('toyota')))

  def test_fresh_plan_is_handed_to_the_controller(self):
    CI = FakeInterface()
    make_card(FakeSubMaster(PLAN)).push_command(CI)
    self.assertEqual(20., CI.CC.cmd.v_target)
    self.assertAlmostEqual(-0.4, CI.CC.cmd.a_target, places=6)
    self.assertTrue(CI.CC.cmd.coast)

  def test_stopped_target_still_counts_as_a_plan(self):
    cmd = make_card(FakeSubMaster({**PLAN, 'vTarget': 0.})).command()
    self.assertEqual(FollowCommand(MIN_PLAN_SPEED, cmd.a_target, True), cmd)

  def test_no_plan_when_stale_invalid_or_inactive(self):
    for sm in (FakeSubMaster(PLAN, age=PLAN_TIMEOUT + 0.1), FakeSubMaster(PLAN, valid=False),
               FakeSubMaster({**PLAN, 'active': False}), FakeSubMaster(None)):
      CI = FakeInterface()
      make_card(sm).push_command(CI)
      self.assertIsNone(CI.CC.cmd)

  def test_shown_set_speed_is_the_estimated_ecm_set_speed(self):
    CI = FakeInterface()
    card = make_card(FakeSubMaster(), CI)
    CS = car.CarState.new_message()
    CS.vCruise = 40.
    CS.vCruiseCluster = 40.
    card.update_car_state(CS)
    self.assertEqual(40., CS.vCruise)
    self.assertEqual(V_CRUISE_UNSET, CS.vCruiseCluster)

    CS.cruiseState.speed = 25.
    CI.CC.display = 87.8
    card.update_car_state(CS)
    self.assertAlmostEqual(90., CS.vCruise, places=3)
    self.assertEqual(88., CS.vCruiseCluster)

  def test_shown_set_speed_ignores_drift_below_a_step(self):
    CI = FakeInterface()
    card = make_card(FakeSubMaster(), CI)
    CS = car.CarState.new_message()
    for estimate, shown in ((99.4, 99.), (99.7, 99.), (99.9, 100.), (99.5, 100.), (97.9, 98.)):
      CI.CC.display = estimate
      card.update_car_state(CS)
      self.assertEqual(shown, CS.vCruiseCluster, estimate)
    CI.CC.display = None
    card.update_car_state(CS)
    self.assertEqual(V_CRUISE_UNSET, CS.vCruiseCluster)

  def test_the_port_controller_takes_the_command(self):
    from opendbc.car.avante_md.interface import CarInterface
    CP = CarInterface.get_non_essential_params("AVANTE_MD_2012")
    CI = CarInterface(CP)
    make_card(FakeSubMaster(PLAN)).push_command(CI)
    self.assertEqual(FollowCommand(20., CI.CC.follow_command.a_target, True), CI.CC.follow_command)
