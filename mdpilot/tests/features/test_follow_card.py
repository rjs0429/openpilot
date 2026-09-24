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


def make_card(sm):
  card = FollowCard.create(car_params())
  card.sm = sm
  card.params = NoStatusParams()
  return card


class FakeController:
  def __init__(self):
    self.cmd = 'unset'

  def set_follow_command(self, cmd):
    self.cmd = cmd


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

  def test_set_speed_shown_while_following(self):
    card = make_card(FakeSubMaster())
    CS = car.CarState.new_message()
    CS.vCruise = 40.
    CS.vCruiseCluster = 40.
    card.update_car_state(CS)
    self.assertEqual(40., CS.vCruise)
    self.assertEqual(V_CRUISE_UNSET, CS.vCruiseCluster)

    CS.cruiseState.speed = 25.
    CS.cruiseState.speedCluster = 25.5
    card.update_car_state(CS)
    self.assertAlmostEqual(90., CS.vCruise, places=3)
    self.assertAlmostEqual(91.8, CS.vCruiseCluster, places=3)

  def test_the_port_controller_takes_the_command(self):
    from opendbc.car.avante_md.interface import CarInterface
    CP = CarInterface.get_non_essential_params("AVANTE_MD_2012")
    CI = CarInterface(CP)
    make_card(FakeSubMaster(PLAN)).push_command(CI)
    self.assertEqual(FollowCommand(20., CI.CC.follow_command.a_target, True), CI.CC.follow_command)
