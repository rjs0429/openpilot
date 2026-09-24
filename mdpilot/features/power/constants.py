"""Power policy for a car that sits for days: shut down an hour after the drive, or sooner when the battery is low."""

# Applied over the same names in openpilot.system.hardware.power_monitoring before hardwared starts.
OVERRIDES = {
  "VBATT_PAUSE_CHARGING": 12.3,
  "MAX_TIME_OFFROAD_S": 60 * 60,
}
