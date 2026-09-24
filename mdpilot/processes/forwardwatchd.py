def main() -> None:
  import time
  try:
    from openpilot.mdpilot.features.forward_watch.daemon import main as run
    run()
  except Exception:
    from openpilot.mdpilot.hooks import report
    report("forward_watch", "forwardwatchd")
  # stay up so the manager does not count a missing process against engagement
  while True:
    time.sleep(1.)
