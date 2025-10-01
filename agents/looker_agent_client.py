"""Looker Agent Client."""
import os
import pandas as pd
from google.cloud import geminidataanalytics
from google.auth import default
from google.auth.transport.requests import Request as gRequest
from google.api_core import exceptions
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

load_dotenv()


class LookerAgentClient:
    """A client for interacting with the Looker Conversational Analytics API."""

    def __init__(
        self,
        project_id: str,
        location: str = "global",
        looker_access_token: str = None,
        looker_client_id: str = os.getenv("LOOKER_CLIENT_ID"),
        looker_client_secret: str = os.getenv("LOOKER_CLIENT_SECRET"),
    ):
        """Initializes the LookerAgentClient."""
        self.project_id = project_id
        self.data_agent_client = geminidataanalytics.DataAgentServiceClient()
        self.data_chat_client = geminidataanalytics.DataChatServiceClient()

        self.location = location

        self.credentials = None
        if looker_client_id and looker_client_secret:
            self.credentials = geminidataanalytics.Credentials(
                oauth=geminidataanalytics.OAuthCredentials(
                    secret=geminidataanalytics.OAuthCredentials.SecretBased(
                        client_id=looker_client_id, client_secret=looker_client_secret
                    )
                )
            )
        elif looker_access_token:
            self.credentials = geminidataanalytics.Credentials(
                oauth=geminidataanalytics.OAuthCredentials(
                    token=geminidataanalytics.OAuthCredentials.TokenBased(
                        access_token=looker_access_token
                    )
                )
            )
        else:
            token = self._get_auth_token()
            if token:
                self.credentials = geminidataanalytics.Credentials(
                    oauth=geminidataanalytics.OAuthCredentials(
                        token=geminidataanalytics.OAuthCredentials.TokenBased(
                            access_token=token
                        )
                    )
                )

    def _get_auth_token(self):
        """Gets the auth token using Application Default Credentials."""
        credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        auth_req = gRequest()
        credentials.refresh(auth_req)
        if credentials.valid:
            return credentials.token
        return None

    def _build_context(
        self,
        system_instruction: str,
        looker_instance_uri: str,
        lookml_model: str,
        explore: str,
        enable_python_analysis: bool = False,
    ) -> geminidataanalytics.Context:
        """Builds the context for the agent."""
        looker_explore_reference = geminidataanalytics.LookerExploreReference()
        looker_explore_reference.looker_instance_uri = looker_instance_uri
        looker_explore_reference.lookml_model = lookml_model
        looker_explore_reference.explore = explore

        datasource_references = geminidataanalytics.DatasourceReferences()
        datasource_references.looker.explore_references = [
            looker_explore_reference
        ]

        context = geminidataanalytics.Context()
        context.system_instruction = system_instruction
        context.datasource_references = datasource_references
        conversation_options = geminidataanalytics.ConversationOptions()
        if enable_python_analysis:
            conversation_options.analysis = geminidataanalytics.AnalysisOptions()
            conversation_options.analysis.python = (
                geminidataanalytics.PythonAnalysisOptions()
            )
            conversation_options.analysis.python.enabled = True
        context.options = conversation_options

        if enable_python_analysis:  
            context.options.analysis.python.enabled = True
        
        return context

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
        published_context = self._build_context(
            system_instruction,
            looker_instance_uri,
            lookml_model,
            explore,
            enable_python_analysis,
        )

        data_agent = geminidataanalytics.DataAgent()
        data_agent.data_analytics_agent.published_context = published_context
        agent_name = f"projects/{self.project_id}/locations/{self.location}/dataAgents/{agent_id}"
        data_agent.name = agent_name

        request = geminidataanalytics.CreateDataAgentRequest(
            parent=f"projects/{self.project_id}/locations/{self.location}",
            data_agent_id=agent_id,
            data_agent=data_agent,
        )

        # print(request)

        # TODO: fix logic to CRUD + CLI simplicity
        try:
            agent = self.data_agent_client.create_data_agent(request=request)
            return agent
        except exceptions.AlreadyExists:
            logger.debug("Data Agent already exists, retrieving it.")
            return self.data_agent_client.get_data_agent(name=agent_name)
        except Exception as e:
            logger.error(f"Error creating Data Agent: {e}")
            return None

    def create_conversation(self, agent_id: str, conversation_id: str):
        """Creates a new conversation."""
        conversation = geminidataanalytics.Conversation()
        conversation.agents = [
            f"projects/{self.project_id}/locations/{self.location}/dataAgents/{agent_id}"
        ]
        conversation_name = f"projects/{self.project_id}/locations/{self.location}/conversations/{conversation_id}"
        conversation.name = conversation_name

        request = geminidataanalytics.CreateConversationRequest(
            parent=f"projects/{self.project_id}/locations/{self.location}",
            conversation_id=conversation_id,
            conversation=conversation,
        )
        logger.debug(f"create conversation request: {request}")

        try:
            response = self.data_chat_client.create_conversation(request=request)
            logger.debug(f"create conversation response: {response}")
            return response
        except exceptions.AlreadyExists:
            logger.debug("Conversation already exists, retrieving it.")
            return self.data_chat_client.get_conversation(name=conversation_name)

    def chat(
        self,
        question: str,
        system_instruction: str,
        skip_agent_use: bool = False,
        agent_id: str = None,
        conversation_id: str = None,
    ) -> tuple[str | None, pd.DataFrame | None, dict | None, str | None]:
        """Sends a message to a conversation and returns the generated SQL and DataFrame."""
        # messages = [geminidataanalytics.Message()]
        # messages[0].user_message.text = question
        messages = [
            geminidataanalytics.Message(
                user_message=geminidataanalytics.UserMessage(text=question)
            )
        ]
        if skip_agent_use:
            # This will need to be updated to pass the looker details to the chat call if we want to support skip_agent_use
            raise NotImplementedError("skip_agent_use is not yet supported with this client version")
        else:
            # print("using a conversation to chat")
            conversation_reference = geminidataanalytics.ConversationReference(
                conversation=f"projects/{self.project_id}/locations/{self.location}/conversations/{conversation_id}",
                data_agent_context=geminidataanalytics.DataAgentContext(
                    data_agent=f"projects/{self.project_id}/locations/{self.location}/dataAgents/{agent_id}",
                    credentials=self.credentials,
                ),
            )

            request = geminidataanalytics.ChatRequest(
                parent=f"projects/{self.project_id}/locations/{self.location}",
                messages=messages,
                conversation_reference=conversation_reference,
            )

        logger.debug(f"Chat request: {request}")
        stream = self.data_chat_client.chat(request=request)

        generated_sql = None
        generated_df = None
        generated_looker_query = None
        generated_text = None
        data_rows = []
        fields = []

        for response in stream:
            logger.debug(response)
            if response.system_message:
                data_message = response.system_message.data
                text_message = response.system_message.text
                # print(f"Received data message: {data_message}")
                # print(f"Received text message: {text_message}")
                if "generated_sql" in data_message:
                    if generated_sql is None:
                        generated_sql = ""
                    generated_sql += data_message.generated_sql
                if "generated_looker_query" in data_message:
                    if generated_looker_query is None:
                        generated_looker_query = {}
                    generated_looker_query = data_message.generated_looker_query
                elif "query" in data_message and hasattr(data_message.query, "looker"):
                    if generated_looker_query is None:
                        generated_looker_query = {}
                    generated_looker_query = data_message.query.looker
                if "result" in data_message:
                    if not fields:
                        fields = [
                            field.name for field in data_message.result.schema.fields
                        ]
                    for el in data_message.result.data:
                        row = {field: el[field] for field in fields}
                        data_rows.append(row)
                if text_message:
                    if generated_text is None:
                        generated_text = ""
                    generated_text += str(text_message.parts)
        
        if data_rows:
            generated_df = pd.DataFrame(data_rows)

        return generated_sql, generated_df, generated_looker_query, generated_text
