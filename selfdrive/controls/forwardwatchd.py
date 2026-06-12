#!/usr/bin/env python3
from enum import IntEnum

from cereal import log, messaging
from openpilot.common.realtime import DT_MDL, Priority, config_realtime_process
from openpilot.common.swaglog import cloudlog


# ── Thresholds ────────────────────────────────────────────────────────────────

STANDSTILL_CONFIRM_S       = 3.0   # seconds of continuous standstill before monitoring
LEAD_DEPART_SPEED_MS       = 0.5   # m/s — vLeadK above which lead is considered departing
ALERT_DELAY_ATTENTIVE_S    = 1.0   # seconds to wait before alerting an attentive driver
ALERT_DELAY_DISTRACTED_S   = 0.5   # seconds to wait before alerting an inattentive driver
COOLDOWN_S                 = 3.0   # seconds to suppress re-trigger after an alert

# modelV2.confidence minimum for shouldStop transition to be trusted
SHOULD_STOP_MIN_CONFIDENCE = log.ModelDataV2.ConfidenceClass.yellow


# ── Internal state enum (matches custom.capnp ForwardWatchState.WatchState) ──

class _State(IntEnum):
  IDLE             = 0
  STOPPED_COUNTING = 1
  MONITORING       = 2
  TRIGGERED        = 3
  ALERTING         = 4
  COOLDOWN         = 5


# ── Trigger reason enum (matches custom.capnp ForwardWatchState.TriggerReason) ─

class _TriggerReason(IntEnum):
  NONE     = 0   # none
  LEAD     = 1   # leadDeparted
  STRAIGHT = 2   # signalStraight
  LEFT     = 3   # signalLeft


# ── Core logic ────────────────────────────────────────────────────────────────

class ForwardWatch:
  def __init__(self) -> None:
    self._state          = _State.IDLE
    self._stop_timer     = 0.0
    self._trigger_timer  = 0.0
    self._cooldown_timer = 0.0

    self._should_stop_prev  = False
    self._trigger_reason    = _TriggerReason.NONE
    self._alert_requested   = False
    self._driver_attentive  = True

  # ── Private helpers ────────────────────────────────────────────────────────

  @staticmethod
  def _is_attentive(dm) -> bool:
    vps = dm.visionPolicyState
    return vps.faceDetected and not vps.isDistracted

  def _check_signal_cleared(self, model) -> bool:
    """Detects shouldStop True→False transition with sufficient model confidence."""
    cleared = (
      self._should_stop_prev
      and not model.action.shouldStop
      and model.confidence >= SHOULD_STOP_MIN_CONFIDENCE
    )
    self._should_stop_prev = model.action.shouldStop
    return cleared

  # ── Public API ─────────────────────────────────────────────────────────────

  def update(self, sm) -> None:
    cs    = sm['carState']
    radar = sm['radarState']
    model = sm['modelV2']
    dm    = sm['driverMonitoringState']

    stopped       = cs.standstill
    has_lead      = radar.leadOne.status
    left_blinker  = cs.leftBlinker
    right_blinker = cs.rightBlinker

    signal_cleared = self._check_signal_cleared(model)
    lead_departed  = has_lead and radar.leadOne.vLeadK > LEAD_DEPART_SPEED_MS

    self._driver_attentive = self._is_attentive(dm)
    self._alert_requested  = False

    if self._state == _State.IDLE:
      if stopped:
        self._state      = _State.STOPPED_COUNTING
        self._stop_timer = 0.0

    elif self._state == _State.STOPPED_COUNTING:
      if not stopped:
        self._state = _State.IDLE
      else:
        self._stop_timer += DT_MDL
        if self._stop_timer >= STANDSTILL_CONFIRM_S:
          self._state = _State.MONITORING
          cloudlog.info("forwardwatchd: monitoring activated")

    elif self._state == _State.MONITORING:
      if not stopped:
        self._state = _State.IDLE
      else:
        triggered = False

        if has_lead:
          # Lead-car mode: signal state is ignored; react to lead departure only
          if lead_departed:
            triggered = True
            self._trigger_reason = _TriggerReason.LEAD
        else:
          # Signal mode: right blinker → no alert (turn is signal-independent)
          #              left blinker  → watch left-turn signal
          #              no blinker    → watch straight-ahead signal
          if not right_blinker and signal_cleared:
            triggered = True
            self._trigger_reason = _TriggerReason.LEFT if left_blinker else _TriggerReason.STRAIGHT

        if triggered:
          self._state         = _State.TRIGGERED
          self._trigger_timer = 0.0
          cloudlog.info(f"forwardwatchd: triggered — {self._trigger_reason.name}")

    elif self._state == _State.TRIGGERED:
      if not stopped:
        self._state = _State.IDLE
      else:
        self._trigger_timer += DT_MDL
        delay = ALERT_DELAY_ATTENTIVE_S if self._driver_attentive else ALERT_DELAY_DISTRACTED_S
        if self._trigger_timer >= delay:
          self._state = _State.ALERTING
          cloudlog.info("forwardwatchd: alert threshold reached")

    elif self._state == _State.ALERTING:
      if not stopped:
        # Driver responded — enter cooldown to suppress immediate re-trigger
        self._state          = _State.COOLDOWN
        self._cooldown_timer = 0.0
        cloudlog.info("forwardwatchd: driver responded, entering cooldown")
      else:
        self._alert_requested = True

    elif self._state == _State.COOLDOWN:
      self._cooldown_timer += DT_MDL
      if self._cooldown_timer >= COOLDOWN_S:
        self._state = _State.IDLE

  def publish(self, pm) -> None:
    msg = messaging.new_message('forwardWatchState')
    msg.valid = True
    fw = msg.forwardWatchState

    fw.alertRequested  = self._alert_requested
    # pycapnp rejects IntEnum instances for enum fields; plain int is required
    fw.watchState      = int(self._state)
    fw.triggerReason   = int(self._trigger_reason)
    fw.stopDuration    = self._stop_timer
    fw.driverAttentive = self._driver_attentive

    pm.send('forwardWatchState', msg)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
  config_realtime_process([0, 1, 2, 3], Priority.CTRL_LOW)

  pm = messaging.PubMaster(['forwardWatchState'])
  sm = messaging.SubMaster(
    ['carState', 'radarState', 'modelV2', 'driverMonitoringState'],
    poll='modelV2',
  )

  fw = ForwardWatch()

  while True:
    sm.update()

    if not sm.updated['modelV2']:
      continue

    fw.update(sm)
    fw.publish(pm)


if __name__ == '__main__':
  main()
