"""Keep the real CLI smoke fixture isolated from live infrastructure ownership."""

import json
from pathlib import Path
import unittest

import hcl2


class FixtureOwnershipTests(unittest.TestCase):
    def test_fixture_can_only_describe_one_unconfigured_synthetic_plan(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root / "terraform-roots.json").read_text()), ["plan"])
        with (root / "plan/main.tf").open() as source:
            config = hcl2.load(source)
        self.assertEqual(set(config), {"terraform", "variable", "resource"})
        self.assertEqual(config["terraform"][0]["backend"], [{"azurerm": {}}])
        self.assertEqual(len(config["resource"]), 1)
        self.assertEqual(set(config["resource"][0]), {"azurerm_service_plan"})
        plan = config["resource"][0]["azurerm_service_plan"]["smoke"]
        self.assertEqual(plan["name"], "asp-hd-smoke-dev")
        self.assertEqual(plan["resource_group_name"], "rg-hd-smoke-dev")


if __name__ == "__main__":
    unittest.main()
