"""A client for interacting with the Looker agent via HTTP (v1)."""

import json
import json as json_lib
import logging
import os

from dotenv import load_dotenv
import google.auth
from google.auth import default
from google.auth.transport.requests import Request as gRequest
import pandas as pd
import requests

load_dotenv()

logger = logging.getLogger(__name__)


def is_json(s):
    try:
        json_lib.loads(s)
    except ValueError:
        return False
    return True


class LookerAgentHttpClient:
    """A client for interacting with the Looker agent via the v1 REST API."""

    def __init__(
        self,
        project: str,
        location: str = "global",
        looker_access_token: str = None,
        looker_client_id: str = None,
        looker_client_secret: str = None,
    ):
        """Initializes the LookerAgentHttpClient.

        Args:
            project: The Google Cloud project ID.
            location: The Google Cloud location.
            looker_access_token: The Looker OAuth access token.
            looker_client_id: The Looker API client ID.
            looker_client_secret: The Looker API client secret.
        """
        self.billing_project = project
        self.location = location
        self.creds, self.project_id = google.auth.default()
        self.api_version = "v1"
        self.base_url = "https://geminidataanalytics.googleapis.com"
        self.headers = self._get_headers()

        self.looker_access_token = (
            looker_access_token
            if looker_access_token is not None
            else os.getenv("LOOKER_ACCESS_TOKEN")
        )
        self.looker_client_id = (
            looker_client_id
            if looker_client_id is not None
            else os.getenv("LOOKER_CLIENT_ID")
        )
        self.looker_client_secret = (
            looker_client_secret
            if looker_client_secret is not None
            else os.getenv("LOOKER_CLIENT_SECRET")
        )

        self.looker_credentials = None
        if self.looker_access_token:
            self.looker_credentials = {
                "oauth": {
                    "token": {
                        "access_token": self.looker_access_token,
                    }
                }
            }
        elif self.looker_client_id and self.looker_client_secret:
            self.looker_credentials = {
                "oauth": {
                    "secret": {
                        "client_id": self.looker_client_id,
                        "client_secret": self.looker_client_secret,
                    }
                }
            }

    def exchange_credentials_for_token(self, looker_instance_uri: str) -> str | None:
        """Exchanges Looker client_id and client_secret for an OAuth access_token."""
        if self.looker_access_token:
            return self.looker_access_token
        if not (self.looker_client_id and self.looker_client_secret and looker_instance_uri):
            return None

        login_url = f"{looker_instance_uri.rstrip('/')}/api/4.0/login"
        try:
            response = requests.post(
                login_url,
                data={
                    "client_id": self.looker_client_id,
                    "client_secret": self.looker_client_secret,
                },
                timeout=30,
            )
            response.raise_for_status()
            token = response.json().get("access_token")
            if token:
                self.looker_access_token = token
                self.looker_credentials = {
                    "oauth": {
                        "token": {
                            "access_token": token,
                        }
                    }
                }
                logger.info("Successfully exchanged Looker client credentials for OAuth access token.")
                return token
        except Exception as e:
            logger.warning(
                f"Failed to exchange Looker client credentials for access token at {login_url}: {e}. "
                "Falling back to SecretBased credentials."
            )
        return None

    def _get_access_token(self):
        """Gets a Google Cloud access token."""
        credentials, _ = default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        auth_req = gRequest()
        credentials.refresh(auth_req)
        if credentials.valid:
            return credentials.token
        return None

    def _get_headers(self):
        """Gets the authorization headers."""
        token = self._get_access_token()
        if token:
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        return None

    def create_agent(
        self,
        agent_id: str,
        system_instruction: str,
        looker_instance_uri: str,
        lookml_model: str = None,
        explore: str = None,
        explores: list[tuple[str, str]] = None,
        enable_python_analysis: bool = False,
        looker_golden_queries: list = None,
    ):
        """Creates a new data agent, or updates the existing agent if it already exists."""
        explore_refs = []
        if explores:
            for m, e in explores:
                explore_refs.append(
                    {
                        "looker_instance_uri": looker_instance_uri,
                        "lookml_model": m,
                        "explore": e,
                    }
                )
        elif lookml_model and explore:
            explore_refs.append(
                {
                    "looker_instance_uri": looker_instance_uri,
                    "lookml_model": lookml_model,
                    "explore": explore,
                }
            )

        looker_data_sources = {
            "looker": {
                "explore_references": explore_refs,
            }
        }

        published_context = {
            "datasource_references": looker_data_sources,
            "system_instruction": system_instruction,
            "options": {
                "analysis": {"python": {"enabled": enable_python_analysis}}
            },
        }
        if looker_golden_queries:
            published_context["looker_golden_queries"] = looker_golden_queries

        agent_resource_name = f"projects/{self.billing_project}/locations/{self.location}/dataAgents/{agent_id}"
        data_agent_payload = {
            "name": agent_resource_name,
            "description": "This is the description of data_agent.",
            "data_analytics_agent": {
                "published_context": published_context,
            },
        }

        data_agent_url = f"{self.base_url}/{self.api_version}/projects/{self.billing_project}/locations/{self.location}/dataAgents"
        params = {"data_agent_id": agent_id}

        data_agent_response = requests.post(
            data_agent_url,
            params=params,
            json=data_agent_payload,
            headers=self.headers,
        )

        if data_agent_response.status_code == 200:
            logger.info("Data Agent created successfully!")
            logger.debug(json.dumps(data_agent_response.json(), indent=2))
        elif data_agent_response.status_code == 409:
            logger.info(f"Data Agent '{agent_id}' already exists, updating its context...")
            update_url = f"{self.base_url}/{self.api_version}/{agent_resource_name}"
            update_params = {"updateMask": "data_analytics_agent.published_context"}
            data_agent_response = requests.patch(
                update_url,
                params=update_params,
                json=data_agent_payload,
                headers=self.headers,
            )
            if data_agent_response.status_code == 200:
                logger.info("Data Agent updated successfully!")
            else:
                logger.error(f"Error updating Data Agent: {data_agent_response.status_code}")
                logger.debug(data_agent_response.text)
        else:
            logger.error(f"Error creating Data Agent: {data_agent_response.status_code}")
            logger.debug(data_agent_response.text)
        return data_agent_response

    def create_conversation(self, agent_id: str, conversation_id: str):
        """Creates a new conversation."""
        conversation_url = f"{self.base_url}/{self.api_version}/projects/{self.billing_project}/locations/{self.location}/conversations"

        conversation_payload = {
            "agents": [
                f"projects/{self.billing_project}/locations/{self.location}/dataAgents/{agent_id}"
            ],
            "name": f"projects/{self.billing_project}/locations/{self.location}/conversations/{conversation_id}",
        }
        params = {"conversation_id": conversation_id}

        conversation_response = requests.post(
            conversation_url,
            headers=self.headers,
            params=params,
            json=conversation_payload,
        )
        if conversation_response.status_code == 200:
            logger.info("Conversation created successfully!")
            logger.debug(json.dumps(conversation_response.json(), indent=2))
        else:
            logger.error(f"Error creating Conversation: {conversation_response.status_code}")
            logger.error(conversation_response.text)
        return conversation_response

    def chat(
        self,
        question: str,
        agent_id: str = None,
        conversation_id: str = None,
        system_instruction: str = None,  # for compatibility with sdk client
        skip_agent_use: bool = False,  # for compatibility with sdk client
        enable_dev_mode: bool = False,
        looker_instance_uri: str = None,
        thinking_mode: str = None,
    ) -> tuple[str | None, pd.DataFrame | None, dict | None, str | None]:
        """Sends a chat message to the agent and returns the parsed response."""
        if enable_dev_mode and not self.looker_access_token and looker_instance_uri:
            self.exchange_credentials_for_token(looker_instance_uri)

        chat_url = f"{self.base_url}/{self.api_version}/projects/{self.billing_project}/locations/{self.location}:chat"

        chat_payload = {
            "parent": f"projects/{self.billing_project}/locations/{self.location}",
            "messages": [{"userMessage": {"text": question}}],
            "conversation_reference": {
                "conversation": f"projects/{self.billing_project}/locations/{self.location}/conversations/{conversation_id}",
                "data_agent_context": {
                    "data_agent": f"projects/{self.billing_project}/locations/{self.location}/dataAgents/{agent_id}",
                },
            },
        }
        if self.looker_credentials:
            chat_payload["credentials"] = self.looker_credentials
        if enable_dev_mode:
            chat_payload["looker_settings"] = {"enable_dev_mode": True}
        if thinking_mode:
            mode_key = thinking_mode.strip().upper()
            if mode_key not in ("FAST", "THINKING", "THINKING_MODE_UNSPECIFIED"):
                raise ValueError(
                    f"Invalid thinking_mode '{thinking_mode}'. Expected 'FAST' or 'THINKING'."
                )
            chat_payload["thinking_mode"] = mode_key

        s = requests.Session()
        acc = ""
        full_response = []
        with s.post(
            chat_url, json=chat_payload, headers=self.headers, stream=True
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue

                decoded_line = str(line, encoding="utf-8")

                if decoded_line == "[":
                    continue
                if decoded_line == "]":
                    continue

                if decoded_line.startswith("{"):
                    acc = decoded_line
                elif decoded_line.endswith("}"):
                    acc += decoded_line
                else:
                    acc += decoded_line

                if is_json(acc):
                    data_json = json_lib.loads(acc)
                    full_response.append(data_json)
                    acc = ""

        generated_sql = None
        generated_df = None
        generated_looker_query = None
        generated_text = None
        data_rows = []
        fields = []

        for response_json in full_response:
            logger.debug(response_json)
            if "systemMessage" in response_json:
                system_message = response_json["systemMessage"]
                if "data" in system_message:
                    data_message = system_message["data"]
                    if "generatedSql" in data_message:
                        if generated_sql is None:
                            generated_sql = ""
                        generated_sql += data_message["generatedSql"]
                    if "query" in data_message and "looker" in data_message.get("query", {}):
                        if generated_looker_query is None:
                            generated_looker_query = {}
                        generated_looker_query.update(data_message["query"]["looker"])
                    if "result" in data_message and "data" in data_message["result"]:
                        if not fields:
                            fields = [
                                field["name"]
                                for field in data_message["result"]["schema"]["fields"]
                            ]
                        for el in data_message["result"]["data"]:
                            row = {field: el.get(field) for field in fields}
                            data_rows.append(row)
                if "text" in system_message:
                    text_msg = system_message["text"]
                    text_type = text_msg.get("textType", "TEXT_TYPE_UNSPECIFIED")
                    if text_type in ("FINAL_RESPONSE", "TEXT_TYPE_UNSPECIFIED", None):
                        if generated_text is None:
                            generated_text = ""
                        generated_text += "".join(text_msg.get("parts", []))

        if data_rows:
            generated_df = pd.DataFrame(data_rows)

        return generated_sql, generated_df, generated_looker_query, generated_text
