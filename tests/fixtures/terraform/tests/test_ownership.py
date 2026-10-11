"""Keep the real CLI smoke fixture isolated from live infrastructure ownership."""

import json
from pathlib import Path
import unittest

import hcl2


class FixtureOwnershipTests(unittest.TestCase):
    def test_fixture_can_only_describe_one_unconfigured_synthetic_plan(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root / "terraform-roots.json").read_text()), ["plan", "directory"])
        with (root / "plan/main.tf").open() as source:
            config = hcl2.load(source)
        self.assertEqual(set(config), {"terraform", "variable", "resource"})
        self.assertEqual(config["terraform"][0]["backend"], [{"azurerm": {}}])
        self.assertEqual(len(config["resource"]), 1)
        self.assertEqual(set(config["resource"][0]), {"azurerm_service_plan"})
        plan = config["resource"][0]["azurerm_service_plan"]["smoke"]
        self.assertEqual(plan["name"], "asp-hd-smoke-dev")
        self.assertEqual(plan["resource_group_name"], "rg-hd-smoke-dev")

    def test_directory_fixture_has_only_synthetic_resources_and_no_credentials(self):
        root = Path(__file__).resolve().parents[1]
        with (root / "directory/main.tf").open() as source:
            config = hcl2.load(source)
        self.assertEqual(set(config), {"terraform", "resource"})
        self.assertEqual(config["terraform"][0]["backend"], [{"azurerm": {}}])
        resources = {kind: body["smoke"] for item in config["resource"] for kind, body in item.items()}
        self.assertEqual(set(resources), {"azuread_application", "azapi_resource", "msgraph_resource"})
        self.assertEqual(resources["azapi_resource"]["parent_id"], "/subscriptions/00000000-0000-4000-8000-000000000001")
        self.assertEqual(resources["msgraph_resource"]["url"], "applications")


if __name__ == "__main__":
    unittest.main()
