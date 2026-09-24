"""Withholds lateral control at low speed until the lane lines are clear, and while a blinker is on without a
lane change. Above LOW_SPEED_LATERAL_MAX the low-speed check latches off until the car slows below
LOW_SPEED_LATERAL_MIN."""
from openpilot.mdpilot import manifest
from openpilot.mdpilot.upstream import CV, DT_CTRL, log

LaneChangeState = log.LaneChangeState

LOW_SPEED_LATERAL_MAX = 30 * CV.KPH_TO_MS
LOW_SPEED_LATERAL_MIN = 20 * CV.KPH_TO_MS
LOW_SPEED_LANE_PROB_ENTER = 0.60
LOW_SPEED_LANE_PROB_EXIT = 0.40
LOW_SPEED_LANE_WIDTH_MIN = 2.7
LOW_SPEED_LANE_WIDTH_MAX = 4.2
LOW_SPEED_LANE_CONFIRM_FRAMES = int(0.3 / DT_CTRL)
LOW_SPEED_LANE_DROP_FRAMES = int(0.1 / DT_CTRL)
LOW_SPEED_TURN_ANGLE = 90.0
LOW_SPEED_BLINKER_TURN_ANGLE = 45.0

BLINKER_SUSPEND_FRAMES = int(1.0 / DT_CTRL)


def create(CP):
  return Gate(CP) if manifest.enabled("lateral_gate") and CP.brand == manifest.BRAND else None


class Gate:
  def __init__(self, CP):
    self.CP = CP
    self.low_speed_lat_ready = False
    self.low_speed_lat_latched = False
    self.low_speed_lane_good_frames = 0
    self.low_speed_lane_bad_frames = 0
    self.blinker_no_lc_frames = 0
    self.blinker_lat_suspended = False

  def allowed(self, CS, model_v2) -> bool:
    low_speed_lat_allowed = self._low_speed_lat_allowed(CS, model_v2)
    blinker_lat_allowed = self._blinker_lat_allowed(CS, model_v2)
    return low_speed_lat_allowed and blinker_lat_allowed

  @staticmethod
  def _lane_data(model_v2) -> tuple[float, float] | None:
    if len(model_v2.laneLineProbs) <= 2 or len(model_v2.laneLines) <= 2:
      return None
    if not len(model_v2.laneLines[1].y) or not len(model_v2.laneLines[2].y):
      return None

    lane_prob = min(float(model_v2.laneLineProbs[1]), float(model_v2.laneLineProbs[2]))
    lane_width = float(model_v2.laneLines[2].y[0] - model_v2.laneLines[1].y[0])
    return lane_prob, lane_width

  def _reset_low_speed_lat(self):
    self.low_speed_lat_ready = False
    self.low_speed_lane_good_frames = 0
    self.low_speed_lane_bad_frames = 0

  def _low_speed_lat_allowed(self, CS, model_v2) -> bool:
    if CS.vEgo > LOW_SPEED_LATERAL_MAX:
      self.low_speed_lat_latched = True
    elif CS.vEgo < LOW_SPEED_LATERAL_MIN:
      self.low_speed_lat_latched = False

    if self.CP.notCar or self.low_speed_lat_latched:
      self._reset_low_speed_lat()
      return True

    turning = (abs(CS.steeringAngleDeg) > LOW_SPEED_TURN_ANGLE or
               ((CS.leftBlinker or CS.rightBlinker) and abs(CS.steeringAngleDeg) > LOW_SPEED_BLINKER_TURN_ANGLE))
    if turning:
      self._reset_low_speed_lat()
      return False

    lane_data = self._lane_data(model_v2)
    lane_confirmed = False
    lane_lost = True
    if lane_data is not None:
      lane_prob, lane_width = lane_data
      lane_width_valid = LOW_SPEED_LANE_WIDTH_MIN <= lane_width <= LOW_SPEED_LANE_WIDTH_MAX
      lane_confirmed = lane_prob >= LOW_SPEED_LANE_PROB_ENTER and lane_width_valid
      lane_lost = lane_prob < LOW_SPEED_LANE_PROB_EXIT or not lane_width_valid

    if lane_confirmed:
      self.low_speed_lane_good_frames += 1
      self.low_speed_lane_bad_frames = 0
    elif lane_lost:
      self.low_speed_lane_good_frames = 0
      self.low_speed_lane_bad_frames += 1
    else:
      self.low_speed_lane_good_frames = 0
      self.low_speed_lane_bad_frames = 0

    if self.low_speed_lane_good_frames >= LOW_SPEED_LANE_CONFIRM_FRAMES:
      self.low_speed_lat_ready = True
    if self.low_speed_lane_bad_frames >= LOW_SPEED_LANE_DROP_FRAMES:
      self.low_speed_lat_ready = False

    return self.low_speed_lat_ready

  def _blinker_lat_allowed(self, CS, model_v2) -> bool:
    blinker_on = CS.leftBlinker or CS.rightBlinker
    lc_active = model_v2.meta.laneChangeState != LaneChangeState.off

    if lc_active:
      self.blinker_no_lc_frames = 0
      self.blinker_lat_suspended = False
      return True

    if blinker_on:
      self.blinker_no_lc_frames += 1
      if self.blinker_no_lc_frames >= BLINKER_SUSPEND_FRAMES:
        self.blinker_lat_suspended = True
    else:
      self.blinker_no_lc_frames = 0
      self.blinker_lat_suspended = False

    return not self.blinker_lat_suspended

