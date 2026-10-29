import unittest

from llms.llm_client import merge_streamed_tool_name


class StreamedToolNameTests(unittest.TestCase):
    def test_repeated_full_name_is_not_duplicated(self):
        self.assertEqual(
            merge_streamed_tool_name("engine_search_tool", "engine_search_tool"),
            "engine_search_tool",
        )

    def test_partial_fragments_are_still_appended(self):
        name = merge_streamed_tool_name("engine_", "search_tool")
        self.assertEqual(name, "engine_search_tool")

    def test_longer_full_name_replaces_partial_prefix(self):
        self.assertEqual(
            merge_streamed_tool_name("engine_", "engine_search_tool"),
            "engine_search_tool",
        )

    def test_repeated_suffix_fragment_is_not_added(self):
        self.assertEqual(
            merge_streamed_tool_name("engine_search_tool", "search_tool"),
            "engine_search_tool",
        )


if __name__ == "__main__":
    unittest.main()
