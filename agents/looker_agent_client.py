"""Looker Agent Client."""
import os
import pandas as pd
# TODO: upgrade to default when python sdk cuts over to beta default
# from google.cloud import geminidataanalytics
from google.cloud import geminidataanalytics_v1beta as geminidataanalytics
from google.auth import default
from google.auth.transport.requests import Request as gRequest
from google.api_core import exceptions
from google.protobuf.json_format import MessageToDict
from dotenv import load_dotenv
import logging
import copy
import proto

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
        
    def _value_to_dict(self, v):
        if isinstance(v, proto.marshal.collections.maps.MapComposite):
            return self._map_to_dict(v)
        if isinstance(v, proto.marshal.collections.RepeatedComposite):
            return [self._value_to_dict(el) for el in v]
        if isinstance(v, (int, float, str, bool)):
            return v
        return MessageToDict(v)

    def _map_to_dict(self, d):
        out = {}
        for k in d:
            if isinstance(d[k], proto.marshal.collections.maps.MapComposite):
                out[k] = self._map_to_dict(d[k])
            else:
                out[k] = self._value_to_dict(d[k])
        return out
    
    #TODO - use Looker SDK to get model reference and vis config from qid
    #TODO - use Looker SDK to get SQL for model reference or qid

    def chat(
        self,
        question: str,
        system_instruction: str,
        skip_agent_use: bool = False,
        agent_id: str = None,
        conversation_id: str = None,
    ) -> tuple[str | None, pd.DataFrame | None, dict | None, str | None, dict | None, list | None, list | None]:
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

        log_request = copy.deepcopy(request)
        if log_request.conversation_reference.data_agent_context.credentials and log_request.conversation_reference.data_agent_context.credentials.oauth.secret:
            log_request.conversation_reference.data_agent_context.credentials.oauth.secret.client_id = "[MASKED]"
            log_request.conversation_reference.data_agent_context.credentials.oauth.secret.client_secret = "[MASKED]"
        logger.debug(f"Chat request: {log_request}")
        stream = self.data_chat_client.chat(request=request)

        generated_sql = None
        generated_df = None
        generated_looker_query = None
        generated_text = None
        generated_chart = None
        dimensions = []
        measures = []
        data_rows = []
        fields = []

        # https://cloud.google.com/gemini/docs/conversational-analytics-api/reference/rest/v1alpha/Message
        for response in stream:
            if response.system_message:
                system_message = response.system_message
                data_message = response.system_message.data
                text_message = response.system_message.text
                #TODO: add analysis
                analysis_message = response.system_message.analysis
                # print(f"Received data message: {data_message}")
                # print(f"Received text message: {text_message}")
                if "generated_sql" in data_message:
                    logger.debug(response)
                    if generated_sql is None:
                        generated_sql = ""
                    generated_sql += data_message.generated_sql
                if "generated_looker_query" in data_message:
                    logger.debug(response)
                    # if generated_looker_query is None:
                    #     generated_looker_query = {}
                    generated_looker_query = data_message.generated_looker_query
                elif "query" in data_message and "looker" in data_message.query:
                    generated_looker_query = data_message.query.looker
                    if "datasources" in data_message.query:
                        for ds in data_message.query.datasources:
                            if "schema" in ds:
                                looker_query_field_schema = ds.schema
                                schema_map = {
                                    f.name: f.category
                                    for f in looker_query_field_schema.fields
                                }
                                for field in generated_looker_query.fields:
                                    category = schema_map.get(field)
                                    if category == "DIMENSION":
                                        dimensions.append(field)
                                    elif category == "MEASURE":
                                        measures.append(field)

                if "result" in data_message:
                    logger.debug(response)
                    if not fields:
                        fields = [
                            field.name for field in data_message.result.schema.fields
                        ]
                    for el in data_message.result.data:
                        row = {field: el[field] for field in fields}
                        data_rows.append(row)
                if text_message:
                    # https://cloud.google.com/gemini/docs/conversational-analytics-api/reference/rest/v1alpha/Message#texttype
                    # TODO: improve logic for final response vs intermediate text
                    # system_message {
                    #   text {
                    #     parts: "The product ID for Churchill Cigars is P328."
                    #     text_type: FINAL_RESPONSE
                    #   }
                    # }
                    logger.debug(response)
                    if generated_text is None:
                        generated_text = ""
                    generated_text += str(text_message.parts)
                if "chart" in system_message:
                    logger.debug(response)
                    logger.debug("chart found in response")
                    if "query" in system_message.chart:
                        print(system_message.chart.query.instructions)
                    elif "result" in system_message.chart:
                        vega_config = system_message.chart.result.vega_config
                        generated_chart = self._map_to_dict(vega_config)
                        logger.debug(generated_chart)


        if data_rows:
            generated_df = pd.DataFrame(data_rows)

        return generated_sql, generated_df, generated_looker_query, generated_text, generated_chart, dimensions, measures