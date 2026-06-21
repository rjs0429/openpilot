#!/usr/bin/env python3
import math

from cereal import car, log, messaging
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.forwardwatchd import (
  MONITORING_TIMEOUT_S,
  STANDSTILL_CONFIRM_S,
  ForwardWatch,
  _State,
  _TriggerReason,
)


class FakeParams:
  def __init__(self, enabled=True):
    self.enabled = enabled

  def get_bool(self, key):
    assert key == "ForwardWatchEnabled"
    return self.enabled


def build_sm():
  cs = messaging.new_message('carState').carState
  cs.gearShifter = car.CarState.GearShifter.drive
  cs.standstill = True

  radar = messaging.new_message('radarState').radarState

  model = messaging.new_message('modelV2').modelV2
  model.confidence = log.ModelDataV2.ConfidenceClass.green

  dm = messaging.new_message('driverMonitoringState').driverMonitoringState
  dm.visionPolicyState.faceDetected = True
  dm.visionPolicyState.isDistracted = False

  return {
    'carState': cs,
    'radarState': radar,
    'modelV2': model,
    'driverMonitoringState': dm,
  }


def advance_to_monitoring(fw, sm):
  fw.update(sm)
  for _ in range(math.ceil(STANDSTILL_CONFIRM_S / DT_MDL) + 1):
    fw.update(sm)
    if fw._state == _State.MONITORING:
      return
  raise AssertionError("forward watch did not enter monitoring")


def test_toggle_is_the_enable_gate():
  params = FakeParams(enabled=False)
  fw = ForwardWatch(params)
  sm = build_sm()

  for _ in range(math.ceil(STANDSTILL_CONFIRM_S / DT_MDL) + 2):
    fw.update(sm)
  assert fw._state == _State.IDLE

  params.enabled = True
  advance_to_monitoring(fw, sm)
  assert fw._state == _State.MONITORING

  params.enabled = False
  fw.update(sm)
  assert fw._state == _State.IDLE
  assert not fw._alert_requested


def test_park_cancels_and_drive_rearms():
  fw = ForwardWatch(FakeParams())
  sm = build_sm()
  advance_to_monitoring(fw, sm)

  sm['carState'].gearShifter = car.CarState.GearShifter.park
  fw.update(sm)
  assert fw._state == _State.IDLE

  sm['carState'].gearShifter = car.CarState.GearShifter.drive
  fw.update(sm)
  assert fw._state == _State.STOPPED_COUNTING


def test_timeout_wins_over_departure_trigger():
  fw = ForwardWatch(FakeParams())
  sm = build_sm()
  advance_to_monitoring(fw, sm)

  fw._session_timer = MONITORING_TIMEOUT_S - DT_MDL
  sm['radarState'].leadOne.status = True
  sm['radarState'].leadOne.vLeadK = 1.0
  fw.update(sm)

  assert fw._state == _State.TIMED_OUT
  assert fw._trigger_reason == _TriggerReason.NONE
  assert not fw._alert_requested


def test_timeout_wins_over_signal_change():
  fw = ForwardWatch(FakeParams())
  sm = build_sm()
  advance_to_monitoring(fw, sm)

  fw._should_stop_prev = True
  fw._session_timer = MONITORING_TIMEOUT_S - DT_MDL
  sm['modelV2'].action.shouldStop = False
  fw.update(sm)

  assert fw._state == _State.TIMED_OUT
  assert fw._trigger_reason == _TriggerReason.NONE
  assert not fw._alert_requested


def test_timeout_cancels_active_alert():
  fw = ForwardWatch(FakeParams())
  sm = build_sm()
  fw._state = _State.ALERTING
  fw._session_timer = MONITORING_TIMEOUT_S - DT_MDL

  fw.update(sm)

  assert fw._state == _State.TIMED_OUT
  assert not fw._alert_requested


def test_timeout_does_not_rearm_until_stopped_session_ends():
  fw = ForwardWatch(FakeParams())
  sm = build_sm()
  advance_to_monitoring(fw, sm)

  fw._session_timer = MONITORING_TIMEOUT_S - DT_MDL
  fw.update(sm)
  assert fw._state == _State.TIMED_OUT

  for _ in range(math.ceil(STANDSTILL_CONFIRM_S / DT_MDL) + 2):
    fw.update(sm)
  assert fw._state == _State.TIMED_OUT

  sm['carState'].standstill = False
  fw.update(sm)
  assert fw._state == _State.IDLE

  sm['carState'].standstill = True
  fw.update(sm)
  assert fw._state == _State.STOPPED_COUNTING
