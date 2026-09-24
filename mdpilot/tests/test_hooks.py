"""Keeps the fork's footprint on upstream to the files and lines in manifest.HOOKS, and its code within its rules."""
import ast
import importlib
import subprocess
import sys
import unittest  # noqa: TID251
from pathlib import Path

from openpilot.mdpilot import manifest, processes

REPO = manifest.repo_root()
MDPILOT = Path(importlib.import_module("openpilot.mdpilot").__file__).resolve().parent
OPENDBC = REPO / "opendbc_repo"
PORT_TESTS = OPENDBC / "opendbc" / "car" / "avante_md" / "tests"
# top-level packages of upstream code, whatever layout the repo is in
UPSTREAM_ROOTS = {"cereal", "common", "selfdrive", "system", "tools", "third_party", "openpilot", "opendbc", "msgq", "panda",
                  "rednose", "teleoprtc", "tinygrad"}
ALLOWED_FORK_IMPORTS = ("openpilot.mdpilot", "opendbc.car.avante_md")
# runtime/health must still report when the upstream window itself is broken
WINDOW_EXEMPT = {"runtime/health.py": ("openpilot.common.params", "openpilot.common.swaglog")}
PREIMPORT_ALLOWED = ("openpilot.mdpilot.manifest",)


def resolve(path: str) -> Path:
  found = {c.resolve() for c in (REPO / path, REPO / "openpilot" / path) if c.exists()}
  if len(found) != 1:
    raise FileNotFoundError(f"{path}: expected one file, found {sorted(str(f) for f in found)}")
  return found.pop()


def sources(*dirs: str):
  for d in dirs:
    yield from sorted((MDPILOT / d).rglob("*.py"))


def import_time_nodes(tree: ast.AST):
  """Every node that runs when the module is imported: all but function bodies."""
  stack = [tree]
  while stack:
    node = stack.pop()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
      continue
    yield node
    stack.extend(ast.iter_child_nodes(node))


def imported_modules(tree: ast.AST, import_time_only=False):
  """(line, module) for every import, including importlib.import_module("x") and __import__("x");
  `from a import b` yields a.b, relative imports yield '.'."""
  for node in (import_time_nodes(tree) if import_time_only else ast.walk(tree)):
    if isinstance(node, ast.Import):
      for alias in node.names:
        yield node.lineno, alias.name
    elif isinstance(node, ast.ImportFrom):
      if node.level:
        yield node.lineno, "."
        continue
      for alias in node.names:
        yield node.lineno, f"{node.module}.{alias.name}"
    elif isinstance(node, ast.Call) and ast.unparse(node.func) in ("importlib.import_module", "import_module", "__import__"):
      if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        yield node.lineno, node.args[0].value


def git(*args) -> str | None:
  try:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout
  except (OSError, subprocess.CalledProcessError):
    return None


def defined_test_classes(test_dir: Path, top: Path) -> set[tuple[str, str]]:
  """(module, class) for every Test* class defined in the test files."""
  found = set()
  for path in test_dir.rglob("test_*.py"):
    module = ".".join(path.relative_to(top).with_suffix("").parts)
    for node in ast.parse(path.read_text()).body:
      if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
        found.add((module, node.name))
  return found


def discovered_classes(suite) -> set[tuple[str, str]]:
  found = set()
  for test in suite:
    if isinstance(test, unittest.TestSuite):
      found |= discovered_classes(test)
    else:
      found.add((type(test).__module__, type(test).__name__))
  return found


class TestHooks(unittest.TestCase):
  def test_every_hook_is_in_place_once(self):
    for path, text in manifest.HOOKS:
      with self.subTest(path=path, text=text):
        lines = [line.strip() for line in resolve(path).read_text().splitlines()]
        self.assertEqual(1, lines.count(text.strip()))

  def test_lateral_gate_follows_the_upstream_decision(self):
    tree = ast.parse(resolve("selfdrive/controls/controlsd.py").read_text())
    blocks = [n.body for n in ast.walk(tree) if isinstance(getattr(n, "body", None), list)]
    decided = "self.sm['selfdriveState'].active"
    gate = "CC.latActive = self.md_lat_gate.allowed(CS, model_v2) and CC.latActive"
    assigns = [n for n in ast.walk(tree) if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "CC.latActive"]
    self.assertEqual(2, len(assigns), "upstream decides latActive once and the gate follows; nothing may reassign it")
    for body in blocks:
      for i, stmt in enumerate(body[:-1]):
        if stmt is assigns[0] and decided in ast.unparse(stmt.value):
          self.assertEqual(gate, ast.unparse(body[i + 1]), "the gate must be the statement right after upstream decides latActive")
          return
    self.fail("upstream latActive decision not found in controlsd.py")

  def test_upstream_edits_are_all_listed(self):
    if git("cat-file", "-e", f"{manifest.UPSTREAM_BASE}^{{commit}}") is None:
      self.skipTest("upstream base commit not available")
    changed = set(git("diff", "--name-only", "--no-renames", manifest.UPSTREAM_BASE, "--").split())
    changed |= set(git("ls-files", "--others", "--exclude-standard").split())
    allowed = {path for path, _ in manifest.HOOKS} | {f"openpilot/{path}" for path, _ in manifest.HOOKS}
    unlisted = sorted(f for f in changed if f not in allowed and not f.startswith(manifest.FORK_PATHS))
    self.assertEqual([], unlisted, "upstream files changed outside manifest.HOOKS")


class TestImportRules(unittest.TestCase):
  def test_features_reach_upstream_only_through_the_window(self):
    for path in sources("features", "ui", "runtime"):
      exempt = WINDOW_EXEMPT.get(str(path.relative_to(MDPILOT)), ())
      for lineno, module in imported_modules(ast.parse(path.read_text())):
        if module.split(".")[0] in UPSTREAM_ROOTS and not module.startswith(ALLOWED_FORK_IMPORTS + exempt):
          self.fail(f"{path.relative_to(REPO)}:{lineno} imports {module}; go through openpilot.mdpilot.upstream")

  def test_fork_modules_have_one_name(self):
    for path in MDPILOT.rglob("*.py"):
      for lineno, module in imported_modules(ast.parse(path.read_text())):
        where = f"{path.relative_to(REPO)}:{lineno}"
        self.assertFalse(module.split(".")[0] == "mdpilot", f"{where} imports {module}; use openpilot.mdpilot")

  def test_modules_the_manager_preimports_import_only_the_stdlib(self):
    entries = [MDPILOT / "__init__.py", MDPILOT / "hooks.py", MDPILOT / "manifest.py", MDPILOT / "processes" / "__init__.py",
               MDPILOT / "processes" / "forwardwatchd.py"]
    entries += [MDPILOT / "processes" / f"{m.rsplit('.', 1)[1]}.py" for m, _ in processes.OVERRIDES.values()]
    for path in entries:
      for lineno, module in imported_modules(ast.parse(path.read_text()), import_time_only=True):
        ok = module.split(".")[0] in sys.stdlib_module_names or module in PREIMPORT_ALLOWED
        self.assertTrue(ok, f"{path.relative_to(REPO)}:{lineno} imports {module} at import time")

  def test_process_entries_are_complete(self):
    for module, _ in processes.OVERRIDES.values():
      mod = importlib.import_module(module)
      self.assertTrue(callable(getattr(mod, "main", None)), module)
      self.assertTrue(callable(getattr(mod, "attach", None)), module)
      self.assertTrue(isinstance(getattr(mod, "UPSTREAM", None), str), module)
      self.assertTrue(set(getattr(mod, "FEATURES", ())) <= set(manifest.FEATURES), module)

  def test_symlinked_package_is_committed(self):
    importlib.import_module("openpilot.mdpilot")
    if not (REPO / "openpilot" / "mdpilot").is_symlink():
      return
    listed = git("ls-files", "-s", "openpilot/mdpilot")
    if listed is None:
      self.skipTest("git not available")
    self.assertTrue(listed.startswith("120000 "), "openpilot/mdpilot must be committed as a symlink")


class TestTestFormat(unittest.TestCase):
  def test_unittest_discovers_every_test_class(self):
    for test_dir, top in ((MDPILOT / "tests", REPO), (PORT_TESTS, OPENDBC)):
      with self.subTest(test_dir=str(test_dir.relative_to(REPO))):
        suite = unittest.defaultTestLoader.discover(str(test_dir), pattern="test_*.py", top_level_dir=str(top))
        prefix = "openpilot." if test_dir == MDPILOT / "tests" else ""
        expected = {(m.removeprefix("openpilot."), c) for m, c in defined_test_classes(test_dir, top)
                    if unittest.defaultTestLoader.getTestCaseNames(getattr(importlib.import_module(prefix + m), c))}
        found = {(m.removeprefix("openpilot."), c) for m, c in discovered_classes(suite)}
        self.assertEqual(set(), expected - found, "test classes unittest does not find")

  def test_tests_run_under_unittest(self):
    for test_dir, top, prefix in ((MDPILOT / "tests", REPO, "openpilot."), (PORT_TESTS, OPENDBC, "")):
      for path in sorted(test_dir.rglob("test_*.py")):
        for node in ast.parse(path.read_text()).body:
          if isinstance(node, ast.FunctionDef):
            where = f"{path.relative_to(REPO)}:{node.lineno}"
            self.assertFalse(node.name.startswith("test"), f"{where} module-level test is skipped by unittest")
      for module, name in defined_test_classes(test_dir, top):
        cls = getattr(importlib.import_module(prefix + module), name)
        self.assertTrue(issubclass(cls, unittest.TestCase), f"{module}.{name} is not a TestCase")

if __name__ == "__main__":
  unittest.main()
