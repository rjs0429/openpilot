import unittest  # noqa: TID251
from unittest import mock  # noqa: TID251

from openpilot.mdpilot import manifest, processes
from openpilot.system.manager.process import PythonProcess


def upstream_procs():
  cond = lambda started, params, CP: started  # noqa: E731
  return [PythonProcess(name, f"selfdrive.fake.{name}", cond) for name in (*processes.OVERRIDES, "radard")], cond


class TestProcesses(unittest.TestCase):
  def test_overrides_keep_upstream_conditions(self):
    procs, cond = upstream_procs()
    out = {p.name: p for p in processes.apply(procs)}
    for name, (module, _) in processes.OVERRIDES.items():
      self.assertEqual(module, out[name].module)
      self.assertIs(cond, out[name].should_run)
    self.assertEqual("selfdrive.fake.radard", out["radard"].module)
    self.assertTrue("forwardwatchd" in out)

  def test_upstream_entries_are_not_modified_in_place(self):
    procs, _ = upstream_procs()
    processes.apply(procs)
    self.assertTrue(all(p.module.startswith("selfdrive.fake.") for p in procs))

  def test_switched_off_feature_is_not_attached(self):
    procs, _ = upstream_procs()
    with mock.patch.dict(manifest.FEATURES, {"power": False, "forward_watch": False}):
      out = {p.name: p for p in processes.apply(procs)}
    self.assertEqual("selfdrive.fake.hardwared", out["hardwared"].module)
    self.assertNotIn("forwardwatchd", out)
    self.assertEqual(processes.OVERRIDES["selfdrived"][0], out["selfdrived"].module)

  def test_manager_runs_the_fork_entries(self):
    from openpilot.system.manager.process_config import managed_processes
    for name, (module, _) in processes.OVERRIDES.items():
      self.assertEqual(module, managed_processes[name].module)
    self.assertEqual("openpilot.mdpilot.processes.forwardwatchd", managed_processes["forwardwatchd"].module)
