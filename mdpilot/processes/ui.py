UPSTREAM = "openpilot.selfdrive.ui.ui"
ROAD_VIEW = "openpilot.selfdrive.ui.mici.onroad.augmented_road_view"

FEATURES = ("follow_cruise",)


def attach(ui) -> None:
  import importlib
  from openpilot.mdpilot.ui.hud import build
  road_view = importlib.import_module(ROAD_VIEW)
  road_view.HudRenderer = build(road_view.HudRenderer)


def main() -> None:
  from openpilot.mdpilot.hooks import run_process
  run_process(UPSTREAM, attach, FEATURES)
