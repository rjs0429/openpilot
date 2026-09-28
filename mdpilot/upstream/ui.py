import pyray as rl

from openpilot.selfdrive.ui.mici.widgets.button import BigMultiParamToggle, BigParamControl
from openpilot.selfdrive.ui.ui_state import ui_state

__all__ = ["BigMultiParamToggle", "BigParamControl", "get_time", "ui_state"]


def get_time() -> float:
  """The UI's clock, the one its widgets time their animations with."""
  return rl.get_time()
