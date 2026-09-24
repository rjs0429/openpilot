"""A broken fork feature must leave the upstream process running as stock, and say so."""
import json
import os
import types
import unittest  # noqa: TID251
from unittest import mock  # noqa: TID251

from cereal import car
from openpilot.mdpilot import hooks
from openpilot.mdpilot.processes import card_md, selfdrived_md
from openpilot.mdpilot.runtime import guard, health
from openpilot.mdpilot.runtime.status_alert import StatusAlert


class Boom(Exception):
  pass


def boom(*args, **kwargs):
  raise Boom


class FakeParams:
  def __init__(self, status=None):
    self.store = {} if status is None else {health.STATUS_PARAM: json.dumps(status)}

  def get(self, key):
    return self.store.get(key)

  def put(self, key, value, block=False):
    self.store[key] = value

  def get_param_path(self):
    return "/nonexistent/params/d"


class TestHooksFallBack(unittest.TestCase):
  def test_process_list_survives_a_broken_fork(self):
    procs = [object()]
    with mock.patch.object(hooks.importlib, "import_module", side_effect=Boom), mock.patch.object(hooks, "report") as report:
      self.assertIs(procs, hooks.apply_processes(procs))
    report.assert_called_once()

  def test_upstream_main_runs_when_attaching_fails(self):
    upstream = types.SimpleNamespace(main=mock.Mock())
    with mock.patch.object(hooks.importlib, "import_module", return_value=upstream), \
         mock.patch.object(hooks, "report") as report:
      hooks.run_process("openpilot.selfdrive.selfdrived.selfdrived", boom, ("follow_cruise", "forward_watch"))
    upstream.main.assert_called_once()
    self.assertEqual([mock.call("follow_cruise", "openpilot.selfdrive.selfdrived.selfdrived"),
                      mock.call("forward_watch", "openpilot.selfdrive.selfdrived.selfdrived")], report.call_args_list)

  def test_lateral_gate_allows_when_it_cannot_be_built(self):
    with mock.patch("openpilot.mdpilot.features.lateral_gate.gate.create", side_effect=Boom), \
         mock.patch.object(hooks, "report") as report:
      gate = hooks.LateralGate(None)
    self.assertTrue(gate.allowed(None, None))
    report.assert_called_once()

  def test_lateral_gate_allows_and_switches_off_when_it_fails(self):
    gate = hooks.LateralGate(car.CarParams.new_message().as_reader())
    gate._gate = types.SimpleNamespace(allowed=boom)
    with mock.patch.object(hooks, "report") as report:
      self.assertTrue(gate.allowed(None, None))
      self.assertTrue(gate.allowed(None, None))
    self.assertIsNone(gate._gate)
    report.assert_called_once()

  def test_toggles_survive_a_broken_fork(self):
    with mock.patch.object(hooks.importlib, "import_module", side_effect=Boom), mock.patch.object(hooks, "report"):
      hooks.extend_toggles(object())

  def test_hooks_survive_a_broken_reporter(self):
    with mock.patch("openpilot.mdpilot.runtime.health.report_failure", side_effect=Boom), \
         mock.patch.object(hooks.traceback, "print_exc") as print_exc:
      hooks.report("x", "y")
    print_exc.assert_called_once()

  def test_feature_that_fails_to_attach_is_off_everywhere(self):
    from openpilot.mdpilot import manifest, processes
    from openpilot.system.manager.process import NativeProcess, PythonProcess
    cond = lambda started, params, CP: started  # noqa: E731
    procs = [PythonProcess(name, f"selfdrive.fake.{name}", cond) for name in ("card", "plannerd", "torqued", "hardwared")]
    procs.append(NativeProcess("selfdrived", "x", ["./x"], cond))
    with mock.patch.dict(os.environ, {manifest.OFF_ENV: ""}), mock.patch.object(hooks, "report") as report:
      out = {p.name: p for p in processes.apply(procs)}
      self.assertFalse(manifest.enabled("follow_cruise"))
      self.assertFalse(manifest.enabled("forward_watch"))
    for name in ("card", "plannerd", "selfdrived"):
      self.assertIs(procs[[p.name for p in procs].index(name)], out[name])
    self.assertEqual(processes.OVERRIDES["torqued"][0], out["torqued"].module)
    self.assertNotIn("forwardwatchd", out)
    self.assertEqual({"follow_cruise", "forward_watch"}, {c.args[0] for c in report.call_args_list})

  def test_missing_carrier_switches_its_features_off(self):
    from openpilot.mdpilot import manifest, processes
    from openpilot.system.manager.process import PythonProcess
    cond = lambda started, params, CP: started  # noqa: E731
    procs = [PythonProcess(name, f"selfdrive.fake.{name}", cond) for name in processes.OVERRIDES if name != "selfdrived"]
    with mock.patch.dict(os.environ, {manifest.OFF_ENV: ""}), mock.patch.object(hooks, "report"):
      out = {p.name: p for p in processes.apply(procs)}
    self.assertEqual("selfdrive.fake.card", out["card"].module)
    self.assertEqual(processes.OVERRIDES["hardwared"][0], out["hardwared"].module)

  def test_broken_entry_module_keeps_its_processes_stock(self):
    from openpilot.mdpilot import manifest, processes
    from openpilot.system.manager.process import PythonProcess
    cond = lambda started, params, CP: started  # noqa: E731
    procs = [PythonProcess(name, f"selfdrive.fake.{name}", cond) for name in ("card", "plannerd")]
    real_import = processes.importlib.import_module

    def import_module(name):
      if name == processes.OVERRIDES["card"][0]:
        raise Boom
      return real_import(name)

    with mock.patch.dict(os.environ, {manifest.OFF_ENV: ""}), mock.patch.object(hooks, "report"), \
         mock.patch.object(processes.importlib, "import_module", side_effect=import_module):
      out = {p.name: p for p in processes.apply(procs)}
    self.assertEqual("selfdrive.fake.card", out["card"].module)
    self.assertEqual("selfdrive.fake.plannerd", out["plannerd"].module)

  def test_forwardwatchd_entry_is_checked(self):
    from openpilot.mdpilot import manifest, processes
    real_import = processes.importlib.import_module

    def import_module(name):
      if name == processes.FORWARDWATCHD:
        raise Boom
      return real_import(name)

    with mock.patch.dict(os.environ, {manifest.OFF_ENV: ""}), mock.patch.object(hooks, "report"), \
         mock.patch.object(processes.importlib, "import_module", side_effect=import_module):
      self.assertEqual([], processes.new_processes())
      self.assertFalse(manifest.enabled("forward_watch"))

  def test_forwardwatchd_stays_up_after_a_failure(self):
    from openpilot.mdpilot.processes import forwardwatchd

    class Stop(BaseException):
      pass

    with mock.patch("openpilot.mdpilot.features.forward_watch.daemon.main", side_effect=Boom), \
         mock.patch.object(hooks, "report") as report, mock.patch("time.sleep", side_effect=Stop):
      with self.assertRaises(Stop):
        forwardwatchd.main()
    report.assert_called_once_with("forward_watch", "forwardwatchd")


class TestGuard(unittest.TestCase):
  def test_first_exception_switches_the_feature_off(self):
    obj = types.SimpleNamespace(work=boom, ok=lambda: 1)
    with mock.patch.object(guard, "_report") as report:
      g = guard.Guarded(obj, "f", "p")
      self.assertEqual([], g.call("work", default=[]))
      self.assertFalse(g.active)
      self.assertIsNone(g.call("ok"))
    report.assert_called_once_with("f", "p")

  def test_failing_factory_leaves_the_feature_off(self):
    with mock.patch.object(guard, "_report") as report:
      g = guard.guarded(boom, "f", "p")
    self.assertFalse(g.active)
    report.assert_called_once()

  def test_factory_returning_none_is_quiet(self):
    with mock.patch.object(guard, "_report") as report:
      g = guard.guarded(lambda: None, "f", "p")
    self.assertFalse(g.active)
    report.assert_not_called()


class TestHealth(unittest.TestCase):
  def test_failures_accumulate_in_the_status_param(self):
    params = FakeParams()
    with mock.patch.object(health, "Params", return_value=params):
      health.report_failure("follow_cruise", "card")
      health.report_failure("lateral_gate", "controlsd")
    self.assertEqual({"follow_cruise": "card", "lateral_gate": "controlsd"}, health.read_status(params))

  def test_unreadable_status_is_empty(self):
    params = FakeParams()
    params.store[health.STATUS_PARAM] = "not json"
    self.assertEqual({}, health.read_status(params))

  def test_concurrent_reports_keep_every_feature(self):
    import multiprocessing
    from openpilot.common.params import Params
    from openpilot.common.prefix import OpenpilotPrefix
    features = [f"feature{i}" for i in range(4)]
    with OpenpilotPrefix("mdhealth"):
      ctx = multiprocessing.get_context("fork")
      barrier = ctx.Barrier(len(features))

      def report(feature):
        barrier.wait()
        health.report_failure(feature, "test")

      workers = [ctx.Process(target=report, args=(f,)) for f in features]
      for w in workers:
        w.start()
      for w in workers:
        w.join(10)
      self.assertEqual(set(features), set(health.read_status(Params())))

  def test_status_is_written_even_without_a_lock_file(self):
    params = FakeParams()
    with mock.patch.object(health, "Params", return_value=params):
      health.report_failure("follow_cruise", "card")
    self.assertEqual({"follow_cruise": "card"}, health.read_status(params))

  def test_status_alert_names_the_features(self):
    alert = StatusAlert(FakeParams({"lateral_gate": "controlsd", "follow_cruise": "card"}))
    alert.update()
    self.assertEqual(1, len(alert.alerts()))
    self.assertEqual("follow_cruise, lateral_gate", alert.alerts()[0].alert_text_2)
    self.assertEqual([], StatusAlert(FakeParams()).alerts())


class FakeCar:
  def __init__(self):
    self.CP = car.CarParams.new_message().as_reader()
    self.CI = types.SimpleNamespace()
    self.sm = types.SimpleNamespace(all_alive=lambda services: True)
    self.calls = []

  def state_update(self):
    self.calls.append("state_update")
    return "CS", "RD"

  def controls_update(self, CS, CC):
    self.calls.append(("controls_update", CS, CC))


class FakeSelfdriveD:
  def __init__(self, initialized=True, passive=False):
    CP = car.CarParams.new_message()
    CP.passive = passive
    self.CP = CP.as_reader()
    self.initialized = initialized
    self.events = []
    self.sm = types.SimpleNamespace(frame=7)
    self.AM = types.SimpleNamespace(add_many=mock.Mock())
    self.calls = []

  def update_events(self, CS):
    self.calls.append("update_events")

  def update_alerts(self, CS):
    self.calls.append("update_alerts")


class TestProcessClasses(unittest.TestCase):
  def test_car_runs_upstream_even_when_the_feature_breaks(self):
    CarMd = card_md.build(FakeCar)
    with mock.patch.object(guard, "_report"):
      c = CarMd()
      c.md_follow = guard.Guarded(types.SimpleNamespace(update_car_state=boom, push_command=boom), "follow_cruise", "card")
      self.assertEqual(("CS", "RD"), c.state_update())
      c.controls_update("CS", "CC")
    self.assertEqual(["state_update", ("controls_update", "CS", "CC")], c.calls)

  def test_selfdrived_adds_fork_alerts_before_upstream_processes_them(self):
    SelfdriveDMd = selfdrived_md.build(FakeSelfdriveD)
    with mock.patch.object(guard, "_report"):
      s = SelfdriveDMd()
      s.md_forward = guard.Guarded(types.SimpleNamespace(alerts=lambda: ["ready"], update=lambda: None), "forward_watch", "x")
      s.md_follow = guard.Guarded(types.SimpleNamespace(alerts=boom, update_events=boom), "follow_cruise", "x")
      s.md_status = guard.Guarded(None, "status", "x")
      s.update_events("CS")
      s.update_alerts("CS")
    s.AM.add_many.assert_called_once_with(7, ["ready"])
    self.assertEqual(["update_events", "update_alerts"], s.calls)

  def test_selfdrived_features_follow_upstream_event_gating(self):
    SelfdriveDMd = selfdrived_md.build(FakeSelfdriveD)
    for kwargs in ({"initialized": False}, {"passive": True}):
      with self.subTest(**kwargs):
        s = SelfdriveDMd.__new__(SelfdriveDMd)
        FakeSelfdriveD.__init__(s, **kwargs)
        forward = types.SimpleNamespace(alerts=lambda: ["ready"], update=mock.Mock())
        s.md_forward = guard.Guarded(forward, "forward_watch", "x")
        s.md_follow = guard.Guarded(types.SimpleNamespace(alerts=lambda: ["follow"], update_events=mock.Mock()), "f", "x")
        s.md_status = guard.Guarded(types.SimpleNamespace(alerts=lambda: ["status"], update=lambda: None), "status", "x")
        s.update_events("CS")
        s.update_alerts("CS")
        forward.update.assert_not_called()
        s.AM.add_many.assert_called_once_with(7, ["status"])


class TestFollowAllOrNothing(unittest.TestCase):
  def test_card_stops_following_once_any_process_switched_it_off(self):
    from openpilot.mdpilot.features.follow_cruise.card import STATUS_EVERY, FollowCard
    params = FakeParams({"follow_cruise": "selfdrived"})
    card = FollowCard(params)
    card.sm = types.SimpleNamespace(update=lambda timeout=0: None)
    self.assertIsNone(card.command())
    params.store.clear()
    for _ in range(2 * STATUS_EVERY):
      card.command()
    self.assertTrue(card.switched_off)


if __name__ == "__main__":
  unittest.main()
