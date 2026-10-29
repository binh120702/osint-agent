import unittest

from agent.tool_decorator import get_registered_tools, tool


class ToolDecoratorTests(unittest.TestCase):
    def test_tool_exposes_schema_and_invocation_interface(self):
        @tool
        def local_test_tool(value: str, count: int = 1) -> str:
            """Return a value for a local contract test.

            Args:
                value: Text to return.
                count: Number of repetitions.
            """
            return value * count

        self.assertEqual(local_test_tool.name, "local_test_tool")
        self.assertEqual(local_test_tool.invoke({"value": "x", "count": 3}), "xxx")
        self.assertEqual(local_test_tool.invoke(value="ok"), "ok")
        function_schema = local_test_tool.schema["function"]
        self.assertEqual(function_schema["name"], "local_test_tool")
        self.assertEqual(function_schema["parameters"]["required"], ["value"])
        self.assertEqual(get_registered_tools()["local_test_tool"], local_test_tool)

    def test_tool_requires_description(self):
        def undocumented_tool(value: str) -> str:
            return value

        with self.assertRaisesRegex(ValueError, "must have a description"):
            tool(undocumented_tool)

    def test_duplicate_tool_names_are_rejected(self):
        @tool
        def duplicate_test_tool(value: str) -> str:
            """First registration for duplicate-name validation."""
            return value

        def duplicate_test_tool(value: str) -> str:
            """Second registration for duplicate-name validation."""
            return value

        with self.assertRaisesRegex(ValueError, "Duplicate tool name"):
            tool(duplicate_test_tool)


if __name__ == "__main__":
    unittest.main()
