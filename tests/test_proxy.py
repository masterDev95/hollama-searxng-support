import json
import unittest
from unittest.mock import call, patch

import proxy


SAMPLE_RESULT = {
    "title": "Python release news",
    "url": "https://www.python.org/downloads/",
    "content": "Python release information.",
    "published": "2026-11-25",
}


class CreateAnswerTests(unittest.TestCase):
    def test_explicit_web_search_runs_before_model_tool_calling(self) -> None:
        messages = [{"role": "user", "content": "Cherche sur le Web météo Cergy"}]
        with (
            patch("proxy.get_search_results", return_value=[SAMPLE_RESULT]) as search,
            patch(
                "proxy.ollama_chat",
                return_value={
                    "content": json.dumps(
                        {
                            "findings": "La source fournit des informations [1].",
                            "interpretation": "Consultez la source pour les prévisions à jour.",
                            "source_ids": [1],
                        }
                    )
                },
            ) as chat,
        ):
            answer = proxy.create_answer("ornith-1.5:9b", messages)

        search.assert_called_once_with("météo Cergy")
        chat.assert_called_once()
        self.assertTrue(chat.call_args.kwargs["structured"])
        self.assertIn("[Python release news](https://www.python.org/downloads/)", answer)

    def test_recent_question_searches_before_local_synthesis(self) -> None:
        messages = [
            {"role": "user", "content": "Quelles sont les dernières nouveautés de Python ?"}
        ]
        with (
            patch("proxy.get_search_results", return_value=[SAMPLE_RESULT]) as search,
            patch(
                "proxy.ollama_chat",
                return_value={
                    "content": json.dumps(
                        {
                            "findings": "La source indique une nouveauté [1].",
                            "interpretation": "Cette nouveauté est récente.",
                            "source_ids": [1],
                        }
                    )
                },
            ) as chat,
        ):
            answer = proxy.create_answer("qwen3.5:9b", messages)

        self.assertIn("### Informations trouvées", answer)
        self.assertIn("### Interprétation", answer)
        self.assertIn("[Python release news](https://www.python.org/downloads/)", answer)
        search.assert_called_once_with(messages[0]["content"])
        chat.assert_called_once()
        self.assertIn(SAMPLE_RESULT["url"], chat.call_args.args[1][0]["content"])
        self.assertTrue(chat.call_args.kwargs["structured"])

    def test_model_search_tool_result_is_returned_for_synthesis(self) -> None:
        messages = [{"role": "user", "content": "Explain how Python list comprehensions work."}]
        tool_call = {
            "type": "function",
            "function": {
                "name": "search_web",
                "arguments": {"query": "recent Python release"},
            },
        }
        with (
            patch("proxy.get_search_results", return_value=[SAMPLE_RESULT]) as search,
            patch(
                "proxy.ollama_chat",
                side_effect=[
                    {"content": "", "tool_calls": [tool_call]},
                    {
                        "content": json.dumps(
                            {
                                "findings": "The release page reports the update [1].",
                                "interpretation": "This is a recent update.",
                                "source_ids": [1],
                            }
                        )
                    },
                ],
            ) as chat,
        ):
            answer = proxy.create_answer("qwen3.5:9b", messages)

        self.assertIn("[1]", answer)
        self.assertIn("[Python release news](https://www.python.org/downloads/)", answer)
        search.assert_called_once_with("recent Python release")
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(chat.call_args_list[0].kwargs["tools"], proxy.SEARCH_TOOL)
        self.assertTrue(chat.call_args_list[1].kwargs["structured"])
        self.assertIn(SAMPLE_RESULT["url"], chat.call_args_list[1].args[1][-1]["content"])

    def test_multiple_tool_searches_number_sources_without_collision(self) -> None:
        messages = [{"role": "assistant", "content": ""}]
        calls = [
            {
                "function": {
                    "name": "search_web",
                    "arguments": {"query": "first query"},
                }
            },
            {
                "function": {
                    "name": "search_web",
                    "arguments": {"query": "second query"},
                }
            },
        ]
        with patch(
            "proxy.get_search_results",
            side_effect=[[SAMPLE_RESULT], [SAMPLE_RESULT | {"url": "https://example.org/"}]],
        ) as search:
            proxy.execute_tool_calls(messages, {"role": "assistant", "tool_calls": calls}, calls)

        search.assert_has_calls([call("first query"), call("second query")])
        self.assertIn("[1]", messages[-2]["content"])
        self.assertIn("[2]", messages[-1]["content"])

    def test_sourced_answer_rejects_unreturned_source_ids(self) -> None:
        content = json.dumps(
            {
                "findings": "A claim [2].",
                "interpretation": "An interpretation.",
                "source_ids": [2],
            }
        )
        with self.assertRaises(proxy.UpstreamError):
            proxy.render_sourced_answer(content, [SAMPLE_RESULT])

    def test_sourced_answer_adds_citation_markers_for_selected_sources(self) -> None:
        content = json.dumps(
            {
                "findings": "The source reports current conditions.",
                "interpretation": "Check the forecast before travelling.",
                "source_ids": [1],
            }
        )

        answer = proxy.render_sourced_answer(content, [SAMPLE_RESULT])

        self.assertIn("The source reports current conditions. [1]", answer)
        self.assertIn("[Python release news](https://www.python.org/downloads/)", answer)


if __name__ == "__main__":
    unittest.main()
