import unittest  # noqa: TID251

import cereal.messaging as messaging
from cereal import car, log
from openpilot.common.constants import CV
from openpilot.mdpilot.features.lateral_gate.gate import (BLINKER_SUSPEND_FRAMES, LOW_SPEED_LANE_CONFIRM_FRAMES,
                                                          LOW_SPEED_LANE_DROP_FRAMES, create)


def car_params(brand='avante_md', not_car=False):
  CP = car.CarParams.new_message()
  CP.brand = brand
  CP.notCar = not_car
  return CP.as_reader()


def car_state(kph, angle=0., left_blinker=False):
  CS = car.CarState.new_message()
  CS.vEgo = kph * CV.KPH_TO_MS
  CS.steeringAngleDeg = angle
  CS.leftBlinker = left_blinker
  return CS.as_reader()


def model(prob=0.9, width=3.5, lane_change=False):
  m = messaging.new_message('modelV2').modelV2
  m.laneLineProbs = [prob] * 4
  lines = m.init('laneLines', 4)
  for i, y in enumerate((-width * 1.5, -width / 2, width / 2, width * 1.5)):
    lines[i].y = [y]
  if lane_change:
    m.meta.laneChangeState = log.LaneChangeState.laneChangeStarting
  return m.as_reader()


def run(gate, CS, model_v2, frames):
  out = None
  for _ in range(frames):
    out = gate.allowed(CS, model_v2)
  return out


class TestLateralGate(unittest.TestCase):
  def test_only_for_the_fork_car(self):
    self.assertIsNone(create(car_params('toyota')))
    self.assertIsNotNone(create(car_params()))

  def test_not_a_car_is_never_gated(self):
    gate = create(car_params(not_car=True))
    self.assertTrue(gate.allowed(car_state(10.), model(prob=0.)))

  def test_low_speed_needs_confirmed_lanes(self):
    gate = create(car_params())
    self.assertFalse(run(gate, car_state(10.), model(prob=0.1), 5))
    self.assertFalse(run(gate, car_state(10.), model(), LOW_SPEED_LANE_CONFIRM_FRAMES - 1))
    self.assertTrue(run(gate, car_state(10.), model(), 1))
    self.assertFalse(run(gate, car_state(10.), model(prob=0.1), LOW_SPEED_LANE_DROP_FRAMES))

  def test_implausible_lane_width_is_not_a_lane(self):
    gate = create(car_params())
    self.assertFalse(run(gate, car_state(10.), model(width=5.), 2 * LOW_SPEED_LANE_CONFIRM_FRAMES))

  def test_speed_latch_has_hysteresis(self):
    gate = create(car_params())
    self.assertTrue(run(gate, car_state(35.), model(prob=0.), 1))
    self.assertTrue(run(gate, car_state(25.), model(prob=0.), 5))
    self.assertFalse(run(gate, car_state(15.), model(prob=0.), 1))
    self.assertFalse(run(gate, car_state(25.), model(prob=0.), 5))

  def test_sharp_turn_at_low_speed_drops_lateral(self):
    gate = create(car_params())
    self.assertTrue(run(gate, car_state(10.), model(), LOW_SPEED_LANE_CONFIRM_FRAMES))
    self.assertFalse(run(gate, car_state(10., angle=100.), model(), 1))

  def test_blinker_without_lane_change_suspends(self):
    gate = create(car_params())
    self.assertTrue(run(gate, car_state(50., left_blinker=True), model(), BLINKER_SUSPEND_FRAMES - 1))
    self.assertFalse(run(gate, car_state(50., left_blinker=True), model(), 1))
    self.assertTrue(run(gate, car_state(50., left_blinker=True), model(lane_change=True), 1))
    self.assertTrue(run(gate, car_state(50.), model(), 1))
