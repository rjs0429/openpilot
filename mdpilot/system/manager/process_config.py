from cereal import car
from openpilot.common.params import Params
from openpilot.system.manager.process import PythonProcess


def avante_md(started: bool, params: Params, CP: car.CarParams) -> bool:
  return started and CP.brand == 'avante_md'


procs = [
  PythonProcess("followplannerd", "mdpilot.selfdrive.controls.followplannerd", avante_md, restart_if_crash=True),
]
