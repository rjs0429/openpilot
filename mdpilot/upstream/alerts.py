"""Builds onroad alerts that go straight to the AlertManager, so the fork never adds EventName numbers."""
from openpilot.selfdrive.selfdrived.events import ET, Alert, AlertSize, AlertStatus, AudibleAlert, EventName, Priority, VisualAlert
from openpilot.system.hardware import HARDWARE

__all__ = ["ET", "Alert", "AlertSize", "AlertStatus", "AudibleAlert", "EventName", "Priority", "VisualAlert", "is_mici",
           "permanent_alert"]


def is_mici() -> bool:
  return HARDWARE.get_device_type() == 'mici'


def permanent_alert(name: str, text: tuple[str, str], status, size, priority, visual, sound, duration: float) -> Alert:
  """An alert shown whether or not openpilot is engaged, typed as if the event `name` had raised it."""
  alert = Alert(text[0], text[1], status, size, priority, visual, sound, duration)
  alert.alert_type = f"{name}/{ET.PERMANENT}"
  alert.event_type = ET.PERMANENT
  return alert
