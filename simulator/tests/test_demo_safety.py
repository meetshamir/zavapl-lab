import ast
from pathlib import Path
import unittest


DEMO_PATH = Path(__file__).parents[1] / "demo.py"


def call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


class ServiceNowScenarioSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(DEMO_PATH.read_text(encoding="utf-8"))
        cls.functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def assert_incident_created_before(self, scenario_name, disruptive_call):
        calls = [
            (node.lineno, call_name(node.func))
            for node in ast.walk(self.functions[scenario_name])
            if isinstance(node, ast.Call)
        ]
        incident_line = min(
            line for line, name in calls if name == "create_servicenow_incident"
        )
        disruption_line = min(line for line, name in calls if name == disruptive_call)
        self.assertLess(
            incident_line,
            disruption_line,
            f"{scenario_name} must fail closed before calling {disruptive_call}",
        )

    def test_service_now_incident_precedes_every_disruptive_action(self):
        scenarios = {
            "scenario_crash": "run_build_release",
            "scenario_perf": "run_build_release",
            "scenario_config": "run_build_release",
            "scenario_disk": "run",
            "scenario_load": "start",
            "scenario_build_failure": "run_ado_pipeline",
        }
        for scenario_name, disruptive_call in scenarios.items():
            with self.subTest(scenario=scenario_name):
                self.assert_incident_created_before(scenario_name, disruptive_call)


if __name__ == "__main__":
    unittest.main()
