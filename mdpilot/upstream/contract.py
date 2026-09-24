"""Everything the fork assumes about upstream, as checks. tests/test_contract.py runs them all; run it first after
every upstream sync. Each failure names what upstream changed; fix the matching module in upstream/ or processes/."""
import ast
import importlib
import inspect
import os
import textwrap

from openpilot.mdpilot.manifest import repo_root

REPO = repo_root()

# upstream module -> class its main() builds by global name, which processes/ swaps for a subclass
CLASS_SWAPS = {
  "openpilot.selfdrive.car.card": "Car",
  "openpilot.selfdrive.controls.plannerd": "LongitudinalPlanner",
  "openpilot.selfdrive.selfdrived.selfdrived": "SelfdriveD",
}

# (module, class, method, parameters) the fork overrides or calls
METHODS = (
  ("openpilot.selfdrive.car.card", "Car", "state_update", ["self"]),
  ("openpilot.selfdrive.car.card", "Car", "controls_update", ["self", "CS", "CC"]),
  ("openpilot.selfdrive.selfdrived.selfdrived", "SelfdriveD", "update_events", ["self", "CS"]),
  ("openpilot.selfdrive.selfdrived.selfdrived", "SelfdriveD", "update_alerts", ["self", "CS"]),
  ("openpilot.selfdrive.controls.lib.longitudinal_planner", "LongitudinalPlanner", "publish", ["self", "sm", "pm"]),
  ("openpilot.selfdrive.selfdrived.alertmanager", "AlertManager", "add_many", ["self", "frame", "alerts"]),
  ("openpilot.selfdrive.selfdrived.events", "Alert", "__init__", ["self", "alert_text_1", "alert_text_2", "alert_status",
   "alert_size", "priority", "visual_alert", "audible_alert", "duration", "creation_delay"]),
)

# (module, function or class.method, text its source must contain)
SOURCES = (
  ("openpilot.selfdrive.car.card", "Car.controls_update", "self.sm.all_alive(['carControl'])"),
  ("openpilot.selfdrive.car.card", "Car.controls_update", "self.CI.apply("),
  ("openpilot.selfdrive.car.card", "Car.step", "CS, RD = self.state_update()"),
  ("openpilot.selfdrive.selfdrived.selfdrived", "SelfdriveD.update_alerts", "self.AM.add_many(self.sm.frame"),
  ("openpilot.selfdrive.selfdrived.selfdrived", "SelfdriveD.update_alerts", "self.AM.process_alerts("),
  ("openpilot.selfdrive.selfdrived.selfdrived", "SelfdriveD.step", "self.update_events(CS)"),
  ("openpilot.selfdrive.controls.plannerd", "main", "longitudinal_planner.publish(sm, pm)"),
  ("openpilot.selfdrive.locationd.torqued", "TorqueEstimator.__init__", "CP.brand in ALLOWED_CARS"),
)

# processes the fork replaces by name
PROCESSES = ("card", "plannerd", "selfdrived", "torqued", "hardwared")

# services the fork subscribes to or publishes
SERVICES = ("carState", "carControl", "radarState", "modelV2", "driverMonitoringState", "followPlanMD", "forwardWatchState")

# services the follow planner reads from plannerd's own SubMaster
PLANNERD_SERVICES = ("carState", "carControl", "radarState", "modelV2")

# (schema struct path, fields the fork reads or writes)
FIELDS = (
  ("car.CarParams", ("brand", "notCar", "vEgoStopping")),
  ("car.CarState", ("vEgo", "standstill", "gearShifter", "leftBlinker", "rightBlinker", "steeringAngleDeg", "vCruise",
                    "vCruiseCluster", "cruiseState")),
  ("car.CarState.CruiseState", ("speed", "speedCluster")),
  ("car.CarControl", ("orientationNED",)),
  ("log.RadarState", ("leadOne",)),
  ("log.RadarState.LeadData", ("status", "dRel", "vLead", "vLeadK", "yRel", "modelProb")),
  ("log.ModelDataV2", ("laneLines", "laneLineProbs", "meta", "action", "confidence")),
  ("log.XYZTData", ("y",)),
  ("log.ModelDataV2.MetaData", ("laneChangeState",)),
  ("log.ModelDataV2.Action", ("shouldStop",)),
  ("log.DriverMonitoringState", ("visionPolicyState",)),
  ("log.DriverMonitoringState.VisionPolicyState", ("faceDetected", "isDistracted")),
)

# (schema enum path, values the fork uses)
ENUMS = (
  ("car.CarState.GearShifter", ("park",)),
  ("log.ModelDataV2.ConfidenceClass", ("green", "yellow")),
  ("log.LaneChangeState", ("off",)),
)

# SelfdriveD.update_events returns early on these conditions; SelfdriveDMd skips the fork events on the same ones
EVENT_EARLY_RETURNS = ("not self.initialized", "self.CP.passive")

POWER_MONITORING = "openpilot.system.hardware.power_monitoring"
TOGGLES_FILE = "selfdrive/ui/mici/layouts/settings/toggles.py"
TOGGLES_TEXT = ("self._scroller.add_widgets(", "self._refresh_toggles = (", "for key, item in self._refresh_toggles:")


def _attr(obj, dotted: str):
  for part in dotted.split("."):
    obj = getattr(obj, part)
  return obj


def check_imports() -> None:
  for name in ("openpilot.mdpilot.upstream", "openpilot.mdpilot.upstream.planner", "openpilot.mdpilot.upstream.alerts",
               "openpilot.mdpilot.upstream.ui"):
    importlib.import_module(name)


def check_class_swaps() -> None:
  for module, cls in CLASS_SWAPS.items():
    mod = importlib.import_module(module)
    assert inspect.isclass(getattr(mod, cls, None)), f"{module} no longer defines {cls}"
    assert cls in mod.main.__code__.co_names, f"{module}.main() no longer builds {cls} by its global name"


def check_methods() -> None:
  for module, cls, method, params in METHODS:
    fn = getattr(getattr(importlib.import_module(module), cls), method, None)
    assert fn is not None, f"{module}.{cls}.{method} is gone"
    got = list(inspect.signature(fn).parameters)
    assert got == params, f"{module}.{cls}.{method} takes {got}, the fork expects {params}"


def check_sources() -> None:
  for module, dotted, text in SOURCES:
    src = inspect.getsource(_attr(importlib.import_module(module), dotted))
    assert text in src, f"{module}.{dotted} no longer contains {text!r}"


def check_processes() -> None:
  from openpilot.mdpilot import manifest, processes
  from openpilot.system.manager import process_config
  from openpilot.system.manager.process import PythonProcess
  assert "module" in inspect.signature(PythonProcess.__init__).parameters, "PythonProcess no longer takes a module"
  managed = process_config.managed_processes
  missing = [name for name in PROCESSES if name not in managed]
  assert not missing, f"upstream no longer has the processes {missing}"
  off = os.environ.get(manifest.OFF_ENV)
  assert not off, f"process_config switched off {off}: a fork process entry could not be set up"
  for name, (entry, features) in processes.OVERRIDES.items():
    if not any(manifest.FEATURES.get(f) for f in features):
      continue
    processes._check(managed[name], (entry, features))
    stock = getattr(managed[name], "stock_module", None)
    assert stock is not None, f"{name} was not attached"
    upstream = importlib.import_module(entry).UPSTREAM
    assert stock.removeprefix("openpilot.") == upstream.removeprefix("openpilot."), \
      f"upstream runs {name} from {stock}, the fork attaches to {upstream}"


def _function_ast(module: str, dotted: str) -> ast.AST:
  return ast.parse(textwrap.dedent(inspect.getsource(_attr(importlib.import_module(module), dotted))))


def check_plannerd_services() -> None:
  tree = _function_ast("openpilot.selfdrive.controls.plannerd", "main")
  calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.unparse(n.func).endswith("SubMaster")]
  assert calls and isinstance(calls[0].args[0], ast.List), "plannerd no longer builds a SubMaster from a list"
  subscribed = {e.value for e in calls[0].args[0].elts if isinstance(e, ast.Constant)}
  missing = [s for s in PLANNERD_SERVICES if s not in subscribed]
  assert not missing, f"plannerd no longer subscribes to {missing}"


def check_event_early_returns() -> None:
  tree = _function_ast("openpilot.selfdrive.selfdrived.selfdrived", "SelfdriveD.update_events")
  returns = {ast.unparse(n.test) for n in ast.walk(tree)
             if isinstance(n, ast.If) and n.body and isinstance(n.body[-1], ast.Return)}
  missing = [c for c in EVENT_EARLY_RETURNS if c not in returns]
  assert not missing, f"SelfdriveD.update_events no longer returns early on {missing}"


def check_enums() -> None:
  from cereal import car, log
  from openpilot.common.realtime import Priority
  roots = {"car": car, "log": log}
  for path, values in ENUMS:
    root, *rest = path.split(".")
    have = set(_attr(roots[root], ".".join(rest)).schema.enumerants)
    missing = [v for v in values if v not in have]
    assert not missing, f"{path} lost {missing}"
  assert hasattr(Priority, "CTRL_LOW"), "realtime Priority.CTRL_LOW is gone"


def check_alerts() -> None:
  from openpilot.selfdrive.selfdrived.events import ET, EventName
  assert hasattr(EventName, "fcw"), "EventName.fcw is gone"
  assert ET.PERMANENT == "permanent", "ET.PERMANENT changed"


def check_services() -> None:
  from cereal.services import SERVICE_LIST
  missing = [s for s in SERVICES if s not in SERVICE_LIST]
  assert not missing, f"services missing: {missing}"


def check_fields() -> None:
  from cereal import car, log
  roots = {"car": car, "log": log}
  for path, fields in FIELDS:
    root, *rest = path.split(".")
    struct = _attr(roots[root], ".".join(rest))
    have = set(struct.schema.fields)
    missing = [f for f in fields if f not in have]
    assert not missing, f"{path} lost the fields {missing}"


def check_planner() -> None:
  from opendbc.car.avante_md.interface import CarInterface
  from openpilot.mdpilot.upstream import planner
  CP = CarInterface.get_non_essential_params("AVANTE_MD_2012").as_reader()
  lp = planner.LongitudinalPlanner(CP)
  assert isinstance(planner.final_speed(lp), float)
  assert isinstance(planner.accel_at(lp, 1.0, planner.v_ego_stopping(CP)), float)
  assert isinstance(planner.lead_limited(lp), bool)
  assert isinstance(planner.fcw(lp), bool)


def check_car_controller() -> None:
  from opendbc.car.avante_md.interface import CarInterface
  CI = CarInterface(CarInterface.get_non_essential_params("AVANTE_MD_2012"))
  assert callable(getattr(CI.CC, "set_follow_command", None)), "the car port no longer takes a follow command"


def check_power_monitoring() -> None:
  from openpilot.mdpilot.features.power.constants import OVERRIDES
  pm = importlib.import_module(POWER_MONITORING)
  missing = [name for name in OVERRIDES if not hasattr(pm, name)]
  assert not missing, f"power_monitoring no longer defines {missing}"
  src = inspect.getsource(pm.PowerMonitoring.should_shutdown)
  unread = [name for name in OVERRIDES if name not in src]
  assert not unread, f"PowerMonitoring.should_shutdown no longer reads {unread}"


def check_torqued() -> None:
  torqued = importlib.import_module("openpilot.selfdrive.locationd.torqued")
  assert isinstance(torqued.ALLOWED_CARS, list), "torqued.ALLOWED_CARS is no longer a list"


def check_toggles() -> None:
  path = REPO / TOGGLES_FILE
  if not path.exists():
    path = REPO / "openpilot" / TOGGLES_FILE
  src = path.read_text()
  missing = [text for text in TOGGLES_TEXT if text not in src]
  assert not missing, f"{TOGGLES_FILE} no longer has {missing}"


CHECKS = (check_imports, check_class_swaps, check_methods, check_sources, check_processes, check_plannerd_services,
          check_event_early_returns, check_services, check_fields, check_enums, check_planner, check_car_controller,
          check_power_monitoring, check_torqued, check_toggles, check_alerts)
