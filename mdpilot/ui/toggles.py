from openpilot.mdpilot import manifest
from openpilot.mdpilot.upstream.ui import BigParamControl

# (title, param, feature)
TOGGLES = (
  ("forward departure alert", "ForwardWatchEnabled", "forward_watch"),
)


def extend(layout) -> None:
  """Appends the fork's toggles to the mici toggles page."""
  added = [(param, BigParamControl(title, param)) for title, param, feature in TOGGLES if manifest.enabled(feature)]
  if not added:
    return
  layout._scroller.add_widgets([widget for _, widget in added])
  layout._refresh_toggles = tuple(layout._refresh_toggles) + tuple(added)
