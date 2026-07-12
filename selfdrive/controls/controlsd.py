#!/usr/bin/env python3
import math
from numbers import Number

from cereal import car, log
import cereal.messaging as messaging
from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.common.realtime import config_realtime_process, DT_CTRL, Priority, Ratekeeper
from openpilot.common.swaglog import cloudlog

from opendbc.car.car_helpers import interfaces
from opendbc.car.vehicle_model import VehicleModel
from openpilot.selfdrive.controls.lib.drive_helpers import clip_curvature
from openpilot.selfdrive.controls.lib.latcontrol import LatControl
from openpilot.selfdrive.controls.lib.latcontrol_pid import LatControlPID
from openpilot.selfdrive.controls.lib.latcontrol_angle import LatControlAngle, STEER_ANGLE_SATURATION_THRESHOLD
from openpilot.selfdrive.controls.lib.latcontrol_torque import LatControlTorque
from openpilot.selfdrive.controls.lib.longcontrol import LongControl
from openpilot.selfdrive.modeld.modeld import LAT_SMOOTH_SECONDS
from openpilot.selfdrive.locationd.helpers import PoseCalibrator, Pose

State = log.SelfdriveState.OpenpilotState
LaneChangeState = log.LaneChangeState
LaneChangeDirection = log.LaneChangeDirection

ACTUATOR_FIELDS = tuple(car.CarControl.Actuators.schema.fields.keys())

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


class Controls:
  def __init__(self) -> None:
    self.params = Params()
    cloudlog.info("controlsd is waiting for CarParams")
    self.CP = messaging.log_from_bytes(self.params.get("CarParams", block=True), car.CarParams)
    cloudlog.info("controlsd got CarParams")

    self.CI = interfaces[self.CP.carFingerprint](self.CP)

    self.sm = messaging.SubMaster(['liveDelay', 'liveParameters', 'liveTorqueParameters', 'modelV2', 'selfdriveState',
                                   'liveCalibration', 'livePose', 'longitudinalPlan', 'lateralManeuverPlan', 'carState', 'carOutput',
                                   'driverMonitoringState', 'onroadEvents', 'driverAssistance'], poll='selfdriveState')
    self.pm = messaging.PubMaster(['carControl', 'controlsState'])

    self.steer_limited_by_safety = False
    self.curvature = 0.0
    self.desired_curvature = 0.0
    self.low_speed_lat_ready = False
    self.low_speed_lat_latched = False
    self.low_speed_lane_good_frames = 0
    self.low_speed_lane_bad_frames = 0
    self.blinker_no_lc_frames = 0
    self.blinker_lat_suspended = False

    self.pose_calibrator = PoseCalibrator()
    self.calibrated_pose: Pose | None = None

    self.LoC = LongControl(self.CP)
    self.VM = VehicleModel(self.CP)
    self.LaC: LatControl
    if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
      self.LaC = LatControlAngle(self.CP, self.CI, DT_CTRL)
    elif self.CP.lateralTuning.which() == 'pid':
      self.LaC = LatControlPID(self.CP, self.CI, DT_CTRL)
    elif self.CP.lateralTuning.which() == 'torque':
      self.LaC = LatControlTorque(self.CP, self.CI, DT_CTRL)

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

  def update(self):
    self.sm.update(15)
    if self.sm.updated["liveCalibration"]:
      self.pose_calibrator.feed_live_calib(self.sm['liveCalibration'])
    if self.sm.updated["livePose"]:
      device_pose = Pose.from_live_pose(self.sm['livePose'])
      self.calibrated_pose = self.pose_calibrator.build_calibrated_pose(device_pose)

  def state_control(self):
    CS = self.sm['carState']

    # Update VehicleModel
    lp = self.sm['liveParameters']
    x = max(lp.stiffnessFactor, 0.1)
    sr = max(lp.steerRatio, 0.1)
    self.VM.update_params(x, sr)

    steer_angle_without_offset = math.radians(CS.steeringAngleDeg - lp.angleOffsetDeg)
    self.curvature = -self.VM.calc_curvature(steer_angle_without_offset, CS.vEgo, lp.roll)

    # Update Torque Params
    if self.CP.lateralTuning.which() == 'torque':
      torque_params = self.sm['liveTorqueParameters']
      if self.sm.all_checks(['liveTorqueParameters']) and torque_params.useParams:
        self.LaC.update_live_torque_params(torque_params.latAccelFactorFiltered, torque_params.latAccelOffsetFiltered,
                                           torque_params.frictionCoefficientFiltered)

    long_plan = self.sm['longitudinalPlan']
    model_v2 = self.sm['modelV2']

    CC = car.CarControl.new_message()
    CC.enabled = self.sm['selfdriveState'].enabled

    # Check which actuators can be enabled
    standstill = abs(CS.vEgo) <= max(self.CP.minSteerSpeed, 0.3) or CS.standstill
    low_speed_lat_allowed = self._low_speed_lat_allowed(CS, model_v2)
    blinker_lat_allowed = self._blinker_lat_allowed(CS, model_v2)
    CC.latActive = (self.sm['selfdriveState'].active and
                    not CS.steerFaultTemporary and
                    not CS.steerFaultPermanent and
                    (not standstill or self.CP.steerAtStandstill) and
                    low_speed_lat_allowed and
                    blinker_lat_allowed)
    CC.longActive = CC.enabled and not any(e.overrideLongitudinal for e in self.sm['onroadEvents']) and self.CP.openpilotLongitudinalControl

    actuators = CC.actuators
    actuators.longControlState = self.LoC.long_control_state

    # Enable blinkers while lane changing
    if model_v2.meta.laneChangeState != LaneChangeState.off:
      CC.leftBlinker = model_v2.meta.laneChangeDirection == LaneChangeDirection.left
      CC.rightBlinker = model_v2.meta.laneChangeDirection == LaneChangeDirection.right

    if not CC.latActive:
      self.LaC.reset()
    if not CC.longActive:
      self.LoC.reset()

    # accel PID loop
    pid_accel_limits = self.CI.get_pid_accel_limits(self.CP, CS.vEgo, CS.vCruise * CV.KPH_TO_MS)
    actuators.accel = float(self.LoC.update(CC.longActive, CS, long_plan.aTarget, long_plan.shouldStop, pid_accel_limits))

    # Steering PID loop and lateral MPC
    # Reset desired curvature to current to avoid violating the limits on engage
    if self.sm.valid['lateralManeuverPlan']:
      new_desired_curvature = self.sm['lateralManeuverPlan'].desiredCurvature if CC.latActive else self.curvature
    else:
      new_desired_curvature = model_v2.action.desiredCurvature if CC.latActive else self.curvature
    self.desired_curvature, curvature_limited = clip_curvature(CS.vEgo, self.desired_curvature, new_desired_curvature, lp.roll)
    lat_delay = self.sm["liveDelay"].lateralDelay + LAT_SMOOTH_SECONDS

    actuators.curvature = self.desired_curvature
    steer, steeringAngleDeg, lac_log = self.LaC.update(CC.latActive, CS, self.VM, lp,
                                                       self.steer_limited_by_safety, self.desired_curvature,
                                                       curvature_limited, lat_delay)
    actuators.torque = float(steer)
    actuators.steeringAngleDeg = float(steeringAngleDeg)
    # Ensure no NaNs/Infs
    for p in ACTUATOR_FIELDS:
      attr = getattr(actuators, p)
      if not isinstance(attr, Number):
        continue

      if not math.isfinite(attr):
        cloudlog.error(f"actuators.{p} not finite {actuators.to_dict()}")
        setattr(actuators, p, 0.0)

    return CC, lac_log

  def publish(self, CC, lac_log):
    CS = self.sm['carState']

    # Orientation and angle rates can be useful for carcontroller
    # Only calibrated (car) frame is relevant for the carcontroller
    CC.currentCurvature = self.curvature
    if self.calibrated_pose is not None:
      CC.orientationNED = self.calibrated_pose.orientation.xyz.tolist()
      CC.angularVelocity = self.calibrated_pose.angular_velocity.xyz.tolist()

    CC.cruiseControl.override = CC.enabled and not CC.longActive and self.CP.openpilotLongitudinalControl
    CC.cruiseControl.cancel = CS.cruiseState.enabled and (not CC.enabled or not self.CP.pcmCruise)
    CC.cruiseControl.resume = CC.enabled and CS.cruiseState.standstill and not self.sm['longitudinalPlan'].shouldStop

    hudControl = CC.hudControl
    hudControl.setSpeed = float(CS.vCruiseCluster * CV.KPH_TO_MS)
    hudControl.speedVisible = CC.enabled
    hudControl.lanesVisible = CC.enabled
    hudControl.leadVisible = self.sm['longitudinalPlan'].hasLead
    hudControl.leadDistanceBars = self.sm['selfdriveState'].personality.raw + 1
    hudControl.visualAlert = self.sm['selfdriveState'].alertHudVisual

    hudControl.rightLaneVisible = True
    hudControl.leftLaneVisible = True
    if self.sm.valid['driverAssistance']:
      hudControl.leftLaneDepart = self.sm['driverAssistance'].leftLaneDeparture
      hudControl.rightLaneDepart = self.sm['driverAssistance'].rightLaneDeparture

    if self.sm['selfdriveState'].active:
      CO = self.sm['carOutput']
      if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
        self.steer_limited_by_safety = abs(CC.actuators.steeringAngleDeg - CO.actuatorsOutput.steeringAngleDeg) > \
                                              STEER_ANGLE_SATURATION_THRESHOLD
      else:
        self.steer_limited_by_safety = abs(CC.actuators.torque - CO.actuatorsOutput.torque) > 1e-2

    # TODO: both controlsState and carControl valids should be set by
    #       sm.all_checks(), but this creates a circular dependency

    # controlsState
    dat = messaging.new_message('controlsState')
    dat.valid = CS.canValid
    cs = dat.controlsState

    cs.curvature = self.curvature
    cs.longitudinalPlanMonoTime = self.sm.logMonoTime['longitudinalPlan']
    cs.lateralPlanMonoTime = self.sm.logMonoTime['modelV2']
    cs.desiredCurvature = self.desired_curvature
    cs.longControlState = self.LoC.long_control_state
    cs.upAccelCmd = float(self.LoC.pid.p)
    cs.uiAccelCmd = float(self.LoC.pid.i)
    cs.ufAccelCmd = float(self.LoC.pid.f)
    cs.forceDecel = bool((self.sm['driverMonitoringState'].alertLevel == log.DriverMonitoringState.AlertLevel.three) or
                         (self.sm['selfdriveState'].state == State.softDisabling))

    lat_tuning = self.CP.lateralTuning.which()
    if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
      cs.lateralControlState.angleState = lac_log
    elif lat_tuning == 'pid':
      cs.lateralControlState.pidState = lac_log
    elif lat_tuning == 'torque':
      cs.lateralControlState.torqueState = lac_log

    self.pm.send('controlsState', dat)

    # carControl
    cc_send = messaging.new_message('carControl')
    cc_send.valid = CS.canValid
    cc_send.carControl = CC
    self.pm.send('carControl', cc_send)

  def run(self):
    rk = Ratekeeper(100, print_delay_threshold=None)
    while True:
      self.update()
      CC, lac_log = self.state_control()
      self.publish(CC, lac_log)
      rk.monitor_time()


def main():
  config_realtime_process(4, Priority.CTRL_HIGH)
  controls = Controls()
  controls.run()


if __name__ == "__main__":
  main()
