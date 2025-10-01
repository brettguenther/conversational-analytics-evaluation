"""A client for interacting with the Looker agent via HTTP."""

import json
import json as json_lib
import os
import time
import logging

import google.auth
import google.auth.transport.requests
import pandas as pd
import requests
from google.auth import default
from google.auth.transport.requests import Request as gRequest
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def is_json(s):
    try:
        json_lib.loads(s)
    except ValueError:
        return False
    return True


class LookerAgentHttpClient:
    """A client for interacting with the Looker agent."""

    def __init__(
        self,
        project: str,
        location: str,
        looker_client_id: str = os.getenv("LOOKER_CLIENT_ID"),
        looker_client_secret: str = os.getenv("LOOKER_CLIENT_SECRET"),
    ):
        """Initializes the LookerAgentHttpClient.

        Args:
            project: The Google Cloud project ID.
            location: The Google Cloud location.
            looker_client_id: The Looker API client ID.
            looker_client_secret: The Looker API client secret.
        """
        self.billing_project = project
        self.location = location
        self.creds, self.project_id = google.auth.default()
        self.api_version = "v1beta"
        self.base_url = "https://geminidataanalytics.googleapis.com"
        self.headers = self._get_headers()
        self.looker_credentials = None
        if looker_client_id and looker_client_secret:
            self.looker_credentials = {
                "oauth": {
                    "secret": {
                        "client_id": looker_client_id,
                        "client_secret": looker_client_secret,
                    }
                }
            }

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
        lookml_model: str,
        explore: str,
        enable_python_analysis: bool = False,
    ):
        """Creates a new data agent."""
        looker_data_sources = {
            "looker": {
                "explore_references": [
                    {
                        "looker_instance_uri": looker_instance_uri,
                        "lookml_model": lookml_model,
                        "explore": explore,
                    },
                ],
            }
        }

        data_agent_payload = {
            "name": f"projects/{self.billing_project}/locations/{self.location}/dataAgents/{agent_id}",
            "description": "This is the description of data_agent.",
            "data_analytics_agent": {
                "published_context": {
                    "datasource_references": looker_data_sources,
                    "system_instruction": system_instruction,
                    "options": {
                        "analysis": {"python": {"enabled": enable_python_analysis}}
                    },
                }
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
        agent_id: str,
        conversation_id: str,
        system_instruction: str = None,  # for compatibility with sdk client
        skip_agent_use: bool = False,  # for compatibility with sdk client
    ) -> tuple[str | None, pd.DataFrame | None, dict | None, str | None]:
        """Sends a chat message to the agent and returns the parsed response."""
        chat_url = f"{self.base_url}/{self.api_version}/projects/{self.billing_project}/locations/{self.location}:chat"

        chat_payload = {
            "parent": f"projects/{self.billing_project}/locations/global",
            "messages": [{"userMessage": {"text": question}}],
            "conversation_reference": {
                "conversation": f"projects/{self.billing_project}/locations/{self.location}/conversations/{conversation_id}",
                "data_agent_context": {
                    "data_agent": f"projects/{self.billing_project}/locations/{self.location}/dataAgents/{agent_id}",
                },
            },
        }
        if self.looker_credentials:
            chat_payload["conversation_reference"]["data_agent_context"][
                "credentials"
            ] = self.looker_credentials

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
                    acc = "{"
                    if decoded_line.endswith("}"):
                        acc = decoded_line
                    else:
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
                    if "generatedLookerQuery" in data_message:
                        if generated_looker_query is None:
                            generated_looker_query = {}
                        generated_looker_query.update(data_message["generatedLookerQuery"])
                    elif "query" in data_message and "looker" in data_message.get("query", {}):
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
                    if generated_text is None:
                        generated_text = ""
                    generated_text += "".join(system_message["text"]["parts"])

        if data_rows:
            generated_df = pd.DataFrame(data_rows)

        return generated_sql, generated_df, generated_looker_query, generated_text
