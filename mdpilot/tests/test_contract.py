import unittest  # noqa: TID251

from openpilot.mdpilot.upstream import contract


class TestUpstreamContract(unittest.TestCase):
  def test_contract(self):
    for check in contract.CHECKS:
      with self.subTest(check=check.__name__):
        check()
