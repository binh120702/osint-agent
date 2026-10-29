import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class ToolRegistryTests(unittest.TestCase):
    def test_registry_imports_allowlisted_modules_and_validates_contract(self):
        fake_tool = SimpleNamespace(
            tool_module="tools.pinterest",
            name="fake_lookup",
            schema={"function": {"name": "fake_lookup"}},
            invoke=lambda args: args,
        )
        module_path = SRC_DIR / "tools" / "all_tools.py"
        spec = importlib.util.spec_from_file_location("test_all_tools_registry", module_path)
        module = importlib.util.module_from_spec(spec)
        with patch("importlib.import_module") as import_module:
            spec.loader.exec_module(module)
            module.get_registered_tools = lambda: {"fake_lookup": fake_tool}
            discovered = module.discover_tools()

        self.assertEqual(discovered, {"fake_lookup": fake_tool})
        self.assertEqual(import_module.call_count, 2 * len(module.TOOL_MODULES))
        self.assertEqual(import_module.call_args_list[0].args[0], module.TOOL_MODULES[0])

    def test_registry_rejects_invalid_tool_schema(self):
        fake_tool = SimpleNamespace(
            tool_module="tools.pinterest",
            name="broken_tool",
            schema={"function": {"name": "wrong_name"}},
            invoke=lambda args: args,
        )
        module_path = SRC_DIR / "tools" / "all_tools.py"
        spec = importlib.util.spec_from_file_location("test_all_tools_invalid", module_path)
        module = importlib.util.module_from_spec(spec)
        with patch("importlib.import_module"):
            spec.loader.exec_module(module)
            module.get_registered_tools = lambda: {"broken_tool": fake_tool}
            with self.assertRaisesRegex(ValueError, "invalid function schema"):
                module.discover_tools()


if __name__ == "__main__":
    unittest.main()
