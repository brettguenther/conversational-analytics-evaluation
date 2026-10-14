import os
import unittest
from unittest.mock import MagicMock, patch

from agents.looker_agent_client import LookerAgentClient
from google.api_core import exceptions
from google.cloud import geminidataanalytics_v1 as geminidataanalytics


class TestLookerAgentClient(unittest.TestCase):

    @patch("agents.looker_agent_client.geminidataanalytics.DataChatServiceClient")
    @patch("agents.looker_agent_client.geminidataanalytics.DataAgentServiceClient")
    def test_credentials_precedence_access_token_over_env_secret(
        self, mock_agent_svc, mock_chat_svc
    ):
        """Verify that looker_access_token takes priority over LOOKER_CLIENT_ID/SECRET."""
        with patch.dict(
            os.environ,
            {
                "LOOKER_CLIENT_ID": "env-client-id",
                "LOOKER_CLIENT_SECRET": "env-client-secret",
            },
            clear=False,
        ):
            client = LookerAgentClient(
                project_id="test-proj",
                looker_access_token="explicit-oauth-token",
            )
            self.assertEqual(
                client.credentials.oauth.token.access_token,
                "explicit-oauth-token",
            )
            self.assertFalse(client.credentials.oauth.secret.client_id)

    @patch("agents.looker_agent_client.requests.post")
    @patch("agents.looker_agent_client.geminidataanalytics.DataChatServiceClient")
    @patch("agents.looker_agent_client.geminidataanalytics.DataAgentServiceClient")
    def test_dev_mode_exchanges_secret_for_oauth_token(
        self, mock_agent_svc, mock_chat_svc, mock_post
    ):
        """Verify that enable_dev_mode exchanges client credentials for a TokenBased access_token."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "minted-dev-token"}
        mock_post.return_value = mock_resp

        client = LookerAgentClient(
            project_id="test-proj",
            looker_access_token="",
            looker_client_id="my-id",
            looker_client_secret="my-secret",
        )
        self.assertEqual(client.credentials.oauth.secret.client_id, "my-id")

        mock_chat_svc.return_value.chat.return_value = []
        client.chat(
            question="Total sales?",
            agent_id="agent-1",
            conversation_id="conv-1",
            enable_dev_mode=True,
            looker_instance_uri="https://looker.example.com/",
        )

        mock_post.assert_called_once_with(
            "https://looker.example.com/api/4.0/login",
            data={"client_id": "my-id", "client_secret": "my-secret"},
            timeout=30,
        )
        sent_request = mock_chat_svc.return_value.chat.call_args.kwargs["request"]
        self.assertEqual(
            sent_request.credentials.oauth.token.access_token,
            "minted-dev-token",
        )
        self.assertTrue(sent_request.looker_settings.enable_dev_mode)

    @patch("agents.looker_agent_client.geminidataanalytics.DataChatServiceClient")
    @patch("agents.looker_agent_client.geminidataanalytics.DataAgentServiceClient")
    def test_build_context_golden_queries_and_raw_system_instruction(
        self, mock_agent_svc, mock_chat_svc
    ):
        """Verify golden queries are mapped to v1 LookerGoldenQuery protos and system_instruction remains untouched."""
        client = LookerAgentClient(
            project_id="test-proj",
            looker_access_token="tok",
        )
        raw_instruction = '{"system_instruction": "keep raw", "golden_queries": []}'
        golden_queries_payload = [
            {
                "natural_language_questions": [
                    "What were total sales last week?",
                    "Weekly sales?",
                ],
                "looker_query": {
                    "model": "wiq-labs",
                    "explore": "sales",
                    "fields": ["sales.total_sales"],
                    "filters": [
                        {"field": "sales.transaction_date", "value": "last week"}
                    ],
                    "sorts": ["sales.total_sales desc"],
                    "limit": "100",
                    "query_id": "1234",
                    "client_id": "abcd",
                },
            },
            {
                "question": "Top 5 categories in 2024?",
                "looker_query": {
                    "model": "wiq-labs",
                    "view": "sales",
                    "fields": ["products.category", "sales.total_sales"],
                    "filters": {"sales.calendar_year": 2024},
                    "limit": 5,
                    "query_timezone": "America/Los_Angeles",
                },
            },
        ]

        ctx = client._build_context(
            system_instruction=raw_instruction,
            looker_instance_uri="https://looker.example.com",
            explores=[("wiq-labs", "sales")],
            looker_golden_queries=golden_queries_payload,
        )

        self.assertEqual(ctx.system_instruction, raw_instruction)
        self.assertEqual(len(ctx.looker_golden_queries), 2)

        gq0 = ctx.looker_golden_queries[0]
        self.assertEqual(
            list(gq0.natural_language_questions),
            ["What were total sales last week?", "Weekly sales?"],
        )
        self.assertEqual(gq0.looker_query.model, "wiq-labs")
        self.assertEqual(gq0.looker_query.explore, "sales")
        self.assertEqual(list(gq0.looker_query.fields), ["sales.total_sales"])
        self.assertEqual(len(gq0.looker_query.filters), 1)
        self.assertEqual(gq0.looker_query.filters[0].field, "sales.transaction_date")
        self.assertEqual(gq0.looker_query.filters[0].value, "last week")
        self.assertEqual(gq0.looker_query.limit, "100")
        self.assertEqual(gq0.looker_query.query_id, "1234")
        self.assertEqual(gq0.looker_query.client_id, "abcd")

        gq1 = ctx.looker_golden_queries[1]
        self.assertEqual(
            list(gq1.natural_language_questions), ["Top 5 categories in 2024?"]
        )
        self.assertEqual(gq1.looker_query.explore, "sales")
        self.assertEqual(gq1.looker_query.filters[0].field, "sales.calendar_year")
        self.assertEqual(gq1.looker_query.filters[0].value, "2024")
        self.assertEqual(gq1.looker_query.limit, "5")

    @patch("agents.looker_agent_client.geminidataanalytics.DataChatServiceClient")
    @patch("agents.looker_agent_client.geminidataanalytics.DataAgentServiceClient")
    def test_create_agent_updates_on_already_exists(
        self, mock_agent_svc, mock_chat_svc
    ):
        """Verify create_agent calls update_data_agent when AlreadyExists is raised."""
        mock_agent_client = mock_agent_svc.return_value
        mock_agent_client.create_data_agent.side_effect = exceptions.AlreadyExists(
            "Agent exists"
        )
        expected_agent = geminidataanalytics.DataAgent(
            name="projects/test-proj/locations/global/dataAgents/existing-agent"
        )
        mock_agent_client.update_data_agent.return_value = expected_agent

        client = LookerAgentClient(project_id="test-proj", looker_access_token="tok")
        result = client.create_agent(
            agent_id="existing-agent",
            system_instruction="Updated instruction",
            looker_instance_uri="https://looker.example.com",
            explores=[("wiq-labs", "sales")],
        )

        self.assertEqual(result, expected_agent)
        mock_agent_client.update_data_agent.assert_called_once()
        update_req = mock_agent_client.update_data_agent.call_args.kwargs["request"]
        self.assertEqual(
            update_req.data_agent.data_analytics_agent.published_context.system_instruction,
            "Updated instruction",
        )
        self.assertIn(
            "data_analytics_agent.published_context",
            update_req.update_mask.paths,
        )

    @patch("agents.looker_agent_client.geminidataanalytics.DataChatServiceClient")
    @patch("agents.looker_agent_client.geminidataanalytics.DataAgentServiceClient")
    def test_build_context_from_agent_definition(self, mock_agent_svc, mock_chat_svc):
        """Verify full agent_definition (--agent-file) populates Context and merges overrides."""
        client = LookerAgentClient(project_id="test-proj", looker_access_token="tok")
        agent_def = {
            "display_name": "Sales Analyst",
            "description": "Looker sales agent",
            "data_analytics_agent": {
                "published_context": {
                    "system_instruction": "Base agent instruction",
                    "datasource_references": {
                        "looker": {
                            "explore_references": [
                                {
                                    "looker_instance_uri": "https://looker.example.com",
                                    "lookml_model": "wiq-labs",
                                    "explore": "sales",
                                }
                            ]
                        }
                    },
                    "looker_golden_queries": [
                        {
                            "natural_language_questions": ["Base question?"],
                            "looker_query": {
                                "model": "wiq-labs",
                                "explore": "sales",
                                "fields": ["sales.count"],
                            },
                        }
                    ],
                    "glossary_terms": [
                        {
                            "display_name": "GMV",
                            "description": "Gross Merchandise Value",
                            "synonyms": ["gross sales"],
                        }
                    ],
                }
            },
        }

        ctx = client._build_context(agent_definition=agent_def)
        self.assertEqual(ctx.system_instruction, "Base agent instruction")
        self.assertEqual(
            ctx.datasource_references.looker.explore_references[0].lookml_model,
            "wiq-labs",
        )
        self.assertEqual(len(ctx.looker_golden_queries), 1)
        self.assertEqual(len(ctx.glossary_terms), 1)
        self.assertEqual(ctx.glossary_terms[0].display_name, "GMV")

    @patch("agents.looker_agent_client.geminidataanalytics.DataChatServiceClient")
    @patch("agents.looker_agent_client.geminidataanalytics.DataAgentServiceClient")
    def test_chat_filters_text_type_enum(self, mock_agent_svc, mock_chat_svc):
        """Verify chat() excludes THOUGHT, PROGRESS, and FOLLOWUP_QUESTIONS and joins FINAL_RESPONSE parts cleanly."""
        mock_chat_client = mock_chat_svc.return_value
        mock_chat_client.chat.return_value = [
            geminidataanalytics.Message(
                system_message=geminidataanalytics.SystemMessage(
                    text=geminidataanalytics.TextMessage(
                        parts=["My Thought Process:\n1. Understand Goal"],
                        text_type=geminidataanalytics.TextMessage.TextType.THOUGHT,
                    )
                )
            ),
            geminidataanalytics.Message(
                system_message=geminidataanalytics.SystemMessage(
                    text=geminidataanalytics.TextMessage(
                        parts=["Sampling data from wiq-labs.sales..."],
                        text_type=geminidataanalytics.TextMessage.TextType.PROGRESS,
                    )
                )
            ),
            geminidataanalytics.Message(
                system_message=geminidataanalytics.SystemMessage(
                    text=geminidataanalytics.TextMessage(
                        parts=["## Final Answer\n\n", "Total revenue is $1,234."],
                        text_type=geminidataanalytics.TextMessage.TextType.FINAL_RESPONSE,
                    )
                )
            ),
            geminidataanalytics.Message(
                system_message=geminidataanalytics.SystemMessage(
                    text=geminidataanalytics.TextMessage(
                        parts=["Would you like to break this down by region?"],
                        text_type=geminidataanalytics.TextMessage.TextType.FOLLOWUP_QUESTIONS,
                    )
                )
            ),
        ]

        client = LookerAgentClient(project_id="test-proj", looker_access_token="tok")
        _, _, _, generated_text, _, _, _ = client.chat(
            question="What is total revenue?",
            skip_agent_use=True,
            looker_instance_uri="https://looker.example.com",
            explores=[("wiq-labs", "sales")],
        )

        self.assertEqual(generated_text, "## Final Answer\n\nTotal revenue is $1,234.")

    @patch("agents.looker_agent_client.geminidataanalytics.DataChatServiceClient")
    @patch("agents.looker_agent_client.geminidataanalytics.DataAgentServiceClient")
    def test_chat_thinking_mode(self, mock_agent_svc, mock_chat_svc):
        """Verify chat() maps FAST and THINKING modes to ChatRequest.ThinkingMode enum and rejects invalid modes."""
        mock_chat_client = mock_chat_svc.return_value
        mock_chat_client.chat.return_value = []

        client = LookerAgentClient(project_id="test-proj", looker_access_token="tok")

        for mode_str, expected_enum in [
            ("FAST", geminidataanalytics.ChatRequest.ThinkingMode.FAST),
            ("thinking", geminidataanalytics.ChatRequest.ThinkingMode.THINKING),
        ]:
            client.chat(
                question="What is total revenue?",
                skip_agent_use=True,
                looker_instance_uri="https://looker.example.com",
                explores=[("wiq-labs", "sales")],
                thinking_mode=mode_str,
            )
            chat_req = mock_chat_client.chat.call_args.kwargs["request"]
            self.assertEqual(chat_req.thinking_mode, expected_enum)

        with self.assertRaises(ValueError):
            client.chat(
                question="What is total revenue?",
                skip_agent_use=True,
                looker_instance_uri="https://looker.example.com",
                explores=[("wiq-labs", "sales")],
                thinking_mode="INVALID_MODE",
            )


if __name__ == "__main__":
    unittest.main()
