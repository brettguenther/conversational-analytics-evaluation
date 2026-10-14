"""Looker Agent Client."""
import copy
import logging
import os
import pandas as pd
import proto
import requests
from dotenv import load_dotenv
from google.api_core import exceptions
from google.api_core import operation as ga_operation
from google.cloud import geminidataanalytics_v1 as geminidataanalytics
from google.protobuf import field_mask_pb2
from google.protobuf.json_format import MessageToDict

logger = logging.getLogger(__name__)

load_dotenv()


class LookerAgentClient:
    """A client for interacting with the Looker Conversational Analytics API (v1)."""

    def __init__(
        self,
        project_id: str,
        location: str = "global",
        looker_access_token: str = None,
        looker_client_id: str = None,
        looker_client_secret: str = None,
    ):
        """Initializes the LookerAgentClient."""
        self.project_id = project_id
        self.location = location
        self.data_agent_client = geminidataanalytics.DataAgentServiceClient()
        self.data_chat_client = geminidataanalytics.DataChatServiceClient()

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

        self.credentials = None
        if self.looker_access_token:
            self.credentials = geminidataanalytics.Credentials(
                oauth=geminidataanalytics.OAuthCredentials(
                    token=geminidataanalytics.OAuthCredentials.TokenBased(
                        access_token=self.looker_access_token
                    )
                )
            )
        elif self.looker_client_id and self.looker_client_secret:
            self.credentials = geminidataanalytics.Credentials(
                oauth=geminidataanalytics.OAuthCredentials(
                    secret=geminidataanalytics.OAuthCredentials.SecretBased(
                        client_id=self.looker_client_id,
                        client_secret=self.looker_client_secret,
                    )
                )
            )

    def exchange_credentials_for_token(self, looker_instance_uri: str) -> str | None:
        """Exchanges Looker client_id and client_secret for an OAuth access_token.

        Used when Looker Dev Mode is enabled and no explicit OAuth access_token
        was provided, ensuring a single shared session token across GDA requests.
        """
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
                self.credentials = geminidataanalytics.Credentials(
                    oauth=geminidataanalytics.OAuthCredentials(
                        token=geminidataanalytics.OAuthCredentials.TokenBased(
                            access_token=token
                        )
                    )
                )
                logger.info("Successfully exchanged Looker client credentials for OAuth access token.")
                return token
        except Exception as e:
            logger.warning(
                f"Failed to exchange Looker client credentials for access token at {login_url}: {e}. "
                "Falling back to SecretBased credentials."
            )
        return None

    @staticmethod
    def _build_looker_query(query_data: dict | geminidataanalytics.LookerQuery) -> geminidataanalytics.LookerQuery:
        """Builds a geminidataanalytics.LookerQuery proto from a dictionary."""
        if isinstance(query_data, geminidataanalytics.LookerQuery):
            return query_data

        model = query_data.get("model", "")
        explore = query_data.get("explore") or query_data.get("view", "")
        fields = list(query_data.get("fields", []))

        raw_filters = query_data.get("filters")
        filters = []
        if isinstance(raw_filters, dict):
            for k, v in raw_filters.items():
                filters.append(
                    geminidataanalytics.LookerQuery.Filter(
                        field=str(k),
                        value="" if v is None else str(v),
                    )
                )
        elif isinstance(raw_filters, list):
            for item in raw_filters:
                if isinstance(item, geminidataanalytics.LookerQuery.Filter):
                    filters.append(item)
                elif isinstance(item, dict) and "field" in item:
                    val = item.get("value")
                    filters.append(
                        geminidataanalytics.LookerQuery.Filter(
                            field=str(item["field"]),
                            value="" if val is None else str(val),
                        )
                    )

        raw_sorts = query_data.get("sorts")
        if isinstance(raw_sorts, list):
            sorts = [str(s) for s in raw_sorts]
        elif isinstance(raw_sorts, str) and raw_sorts:
            sorts = [raw_sorts]
        else:
            sorts = []

        raw_limit = query_data.get("limit")
        limit = str(raw_limit) if raw_limit is not None else None

        raw_dynamic_fields = query_data.get("dynamic_fields") or query_data.get("dynamicFields") or []
        dynamic_fields = []
        valid_df_keys = set(geminidataanalytics.DynamicField.pb().DESCRIPTOR.fields_by_name.keys())
        for df in raw_dynamic_fields:
            if isinstance(df, geminidataanalytics.DynamicField):
                dynamic_fields.append(df)
            elif isinstance(df, dict):
                filtered_df = {k: v for k, v in df.items() if k in valid_df_keys and v is not None}
                dynamic_fields.append(geminidataanalytics.DynamicField(**filtered_df))

        query_kwargs = {
            "model": model,
            "explore": explore,
            "fields": fields,
            "filters": filters,
            "sorts": sorts,
        }
        if limit is not None:
            query_kwargs["limit"] = limit
        if dynamic_fields:
            query_kwargs["dynamic_fields"] = dynamic_fields

        query_id = query_data.get("query_id") or query_data.get("queryId")
        if query_id is not None:
            query_kwargs["query_id"] = str(query_id)

        client_id = query_data.get("client_id") or query_data.get("clientId")
        if client_id is not None:
            query_kwargs["client_id"] = str(client_id)

        return geminidataanalytics.LookerQuery(**query_kwargs)

    @classmethod
    def _build_looker_golden_queries(
        cls,
        golden_queries_data: list | dict | None,
    ) -> list[geminidataanalytics.LookerGoldenQuery]:
        """Builds a list of geminidataanalytics.LookerGoldenQuery protos."""
        if not golden_queries_data:
            return []

        if isinstance(golden_queries_data, dict):
            entries = (
                golden_queries_data.get("looker_golden_queries")
                or golden_queries_data.get("lookerGoldenQueries")
                or golden_queries_data.get("golden_queries")
                or []
            )
        elif isinstance(golden_queries_data, list):
            entries = golden_queries_data
        else:
            return []

        golden_queries = []
        for entry in entries:
            if isinstance(entry, geminidataanalytics.LookerGoldenQuery):
                golden_queries.append(entry)
                continue
            if not isinstance(entry, dict):
                continue

            questions = (
                entry.get("natural_language_questions")
                or entry.get("naturalLanguageQuestions")
                or entry.get("questions")
            )
            if isinstance(questions, str):
                questions = [questions]
            elif not questions:
                single_q = entry.get("question") or entry.get("natural_language_query")
                questions = [single_q] if single_q else []
            else:
                questions = [str(q) for q in questions]

            lq_data = entry.get("looker_query") or entry.get("lookerQuery")
            looker_query = cls._build_looker_query(lq_data) if lq_data else None

            gq_kwargs = {"natural_language_questions": questions}
            if looker_query is not None:
                gq_kwargs["looker_query"] = looker_query
            golden_queries.append(geminidataanalytics.LookerGoldenQuery(**gq_kwargs))

        return golden_queries

    @staticmethod
    def _build_glossary_terms(
        glossary_data: list | None,
    ) -> list[geminidataanalytics.GlossaryTerm]:
        """Builds a list of geminidataanalytics.GlossaryTerm protos."""
        if not glossary_data or not isinstance(glossary_data, list):
            return []

        terms = []
        for item in glossary_data:
            if isinstance(item, geminidataanalytics.GlossaryTerm):
                terms.append(item)
            elif isinstance(item, dict):
                display_name = item.get("display_name") or item.get("displayName") or item.get("term", "")
                description = item.get("description", "")
                labels = list(item.get("labels") or item.get("synonyms") or [])
                terms.append(
                    geminidataanalytics.GlossaryTerm(
                        display_name=display_name,
                        description=description,
                        labels=labels,
                    )
                )
        return terms

    def _build_context(
        self,
        system_instruction: str = None,
        looker_instance_uri: str = None,
        explores: list[tuple[str, str]] = None,
        enable_python_analysis: bool = False,
        looker_golden_queries: list | dict = None,
        agent_definition: dict = None,
    ) -> geminidataanalytics.Context:
        """Builds the v1 Context for the agent."""
        base_context_dict = {}
        if isinstance(agent_definition, dict):
            if "data_analytics_agent" in agent_definition:
                daa = agent_definition["data_analytics_agent"]
                base_context_dict = (
                    daa.get("published_context")
                    or daa.get("publishedContext")
                    or daa.get("staging_context")
                    or daa.get("stagingContext")
                    or {}
                )
            elif "dataAnalyticsAgent" in agent_definition:
                daa = agent_definition["dataAnalyticsAgent"]
                base_context_dict = (
                    daa.get("publishedContext")
                    or daa.get("published_context")
                    or daa.get("stagingContext")
                    or daa.get("staging_context")
                    or {}
                )
            elif "published_context" in agent_definition or "publishedContext" in agent_definition:
                base_context_dict = (
                    agent_definition.get("published_context")
                    or agent_definition.get("publishedContext")
                    or {}
                )
            else:
                base_context_dict = agent_definition

        explore_references = []
        if explores:
            for model, explore in explores:
                looker_explore_reference = geminidataanalytics.LookerExploreReference(
                    looker_instance_uri=looker_instance_uri,
                    lookml_model=model,
                    explore=explore,
                )
                explore_references.append(looker_explore_reference)
        else:
            ds_refs = (
                base_context_dict.get("datasource_references")
                or base_context_dict.get("datasourceReferences")
                or {}
            )
            looker_refs = ds_refs.get("looker", {})
            raw_exp_refs = (
                looker_refs.get("explore_references")
                or looker_refs.get("exploreReferences")
                or []
            )
            for ref in raw_exp_refs:
                if isinstance(ref, geminidataanalytics.LookerExploreReference):
                    explore_references.append(ref)
                elif isinstance(ref, dict):
                    explore_references.append(
                        geminidataanalytics.LookerExploreReference(
                            looker_instance_uri=(
                                ref.get("looker_instance_uri")
                                or ref.get("lookerInstanceUri")
                                or looker_instance_uri
                            ),
                            lookml_model=ref.get("lookml_model") or ref.get("lookmlModel", ""),
                            explore=ref.get("explore", ""),
                        )
                    )

        datasource_references = geminidataanalytics.DatasourceReferences()
        datasource_references.looker.explore_references = explore_references

        context = geminidataanalytics.Context()
        effective_instruction = (
            system_instruction
            if system_instruction is not None
            else (
                base_context_dict.get("system_instruction")
                or base_context_dict.get("systemInstruction")
                or "You are a helpful data assistant."
            )
        )
        context.system_instruction = effective_instruction
        context.datasource_references = datasource_references

        # Golden queries: combine agent_definition golden queries with explicit looker_golden_queries
        combined_golden_queries = []
        base_gq = (
            base_context_dict.get("looker_golden_queries")
            or base_context_dict.get("lookerGoldenQueries")
            or base_context_dict.get("golden_queries")
        )
        if base_gq:
            combined_golden_queries.extend(self._build_looker_golden_queries(base_gq))
        if looker_golden_queries:
            combined_golden_queries.extend(self._build_looker_golden_queries(looker_golden_queries))
        if combined_golden_queries:
            context.looker_golden_queries = combined_golden_queries

        # Glossary terms from agent_definition if present
        base_glossary = (
            base_context_dict.get("glossary_terms")
            or base_context_dict.get("glossaryTerms")
            or base_context_dict.get("glossaries")
        )
        if base_glossary:
            context.glossary_terms = self._build_glossary_terms(base_glossary)

        # Conversation options
        conversation_options = geminidataanalytics.ConversationOptions()
        base_options = base_context_dict.get("options", {})
        base_python_enabled = (
            base_options.get("analysis", {}).get("python", {}).get("enabled", False)
            if isinstance(base_options, dict)
            else False
        )
        if enable_python_analysis or base_python_enabled:
            conversation_options.analysis = geminidataanalytics.AnalysisOptions(
                python=geminidataanalytics.AnalysisOptions.Python(enabled=True)
            )
        context.options = conversation_options

        return context

    @staticmethod
    def _resolve_operation(op):
        """Resolves a google.api_core.operation.Operation to its result if applicable."""
        if isinstance(op, ga_operation.Operation):
            return op.result()
        return op

    def create_agent(
        self,
        agent_id: str,
        system_instruction: str = None,
        looker_instance_uri: str = None,
        explores: list[tuple[str, str]] = None,
        enable_python_analysis: bool = False,
        looker_golden_queries: list | dict = None,
        agent_definition: dict = None,
    ):
        """Creates a new data agent, or updates the existing agent if it already exists."""
        published_context = self._build_context(
            system_instruction=system_instruction,
            looker_instance_uri=looker_instance_uri,
            explores=explores,
            enable_python_analysis=enable_python_analysis,
            looker_golden_queries=looker_golden_queries,
            agent_definition=agent_definition,
        )

        data_agent = geminidataanalytics.DataAgent()
        data_agent.data_analytics_agent.published_context = published_context
        agent_name = f"projects/{self.project_id}/locations/{self.location}/dataAgents/{agent_id}"
        data_agent.name = agent_name

        if isinstance(agent_definition, dict):
            if agent_definition.get("display_name") or agent_definition.get("displayName"):
                data_agent.display_name = (
                    agent_definition.get("display_name") or agent_definition.get("displayName")
                )
            if agent_definition.get("description"):
                data_agent.description = agent_definition["description"]

        request = geminidataanalytics.CreateDataAgentRequest(
            parent=f"projects/{self.project_id}/locations/{self.location}",
            data_agent_id=agent_id,
            data_agent=data_agent,
        )

        try:
            op = self.data_agent_client.create_data_agent(request=request)
            return self._resolve_operation(op)
        except exceptions.AlreadyExists:
            logger.info(f"Data Agent '{agent_id}' already exists, updating its context...")
            update_paths = ["data_analytics_agent.published_context"]
            if data_agent.display_name:
                update_paths.append("display_name")
            if data_agent.description:
                update_paths.append("description")
            update_request = geminidataanalytics.UpdateDataAgentRequest(
                data_agent=data_agent,
                update_mask=field_mask_pb2.FieldMask(paths=update_paths),
            )
            op = self.data_agent_client.update_data_agent(request=update_request)
            return self._resolve_operation(op)
        except Exception as e:
            logger.error(f"Error creating or updating Data Agent: {e}")
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
        if v is None:
            return None
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

    def _get_looker_api_token(self, looker_instance_uri: str) -> str | None:
        """Returns a Looker OAuth access token for direct Looker API calls without mutating GDA credentials."""
        if self.looker_access_token:
            return self.looker_access_token
        if getattr(self, "_cached_looker_api_token", None):
            return self._cached_looker_api_token
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
                self._cached_looker_api_token = token
                return token
        except Exception as e:
            logger.warning(
                f"Failed to obtain Looker API token from {login_url}: {e}"
            )
        return None

    def fetch_looker_sql(
        self,
        looker_query: dict | geminidataanalytics.LookerQuery,
        looker_instance_uri: str = None,
        explores: list[tuple[str, str]] = None,
        agent_definition: dict = None,
    ) -> str | None:
        """Compiles a generated LookerQuery into SQL via the Looker 4.0 inline query API."""
        if not looker_query:
            return None

        if isinstance(looker_query, geminidataanalytics.LookerQuery):
            query_dict = geminidataanalytics.LookerQuery.to_dict(looker_query)
        elif isinstance(looker_query, dict):
            query_dict = dict(looker_query)
        else:
            return None

        resolved_uri = looker_instance_uri
        default_model = None
        default_explore = None
        if explores:
            default_model, default_explore = explores[0]
        elif isinstance(agent_definition, dict):
            ctx = self._build_context(agent_definition=agent_definition)
            exp_refs = ctx.datasource_references.looker.explore_references
            if exp_refs:
                resolved_uri = resolved_uri or exp_refs[0].looker_instance_uri
                default_model = exp_refs[0].lookml_model
                default_explore = exp_refs[0].explore

        if not resolved_uri:
            return None

        token = self._get_looker_api_token(resolved_uri)
        if not token:
            return None

        model = query_dict.get("model") or default_model
        view = query_dict.get("explore") or query_dict.get("view") or default_explore
        fields = list(query_dict.get("fields") or [])
        if not (model and view and fields):
            return None

        raw_filters = query_dict.get("filters")
        sdk_filters = {}
        if isinstance(raw_filters, list):
            for f in raw_filters:
                if isinstance(f, dict) and "field" in f and "value" in f:
                    sdk_filters[str(f["field"])] = str(f["value"])
        elif isinstance(raw_filters, dict):
            sdk_filters = {str(k): str(v) for k, v in raw_filters.items()}

        write_query: dict = {
            "model": model,
            "view": view,
            "fields": fields,
        }
        if sdk_filters:
            write_query["filters"] = sdk_filters
        if query_dict.get("sorts"):
            write_query["sorts"] = list(query_dict["sorts"])
        if query_dict.get("limit") is not None:
            write_query["limit"] = str(query_dict["limit"])

        sql_url = f"{resolved_uri.rstrip('/')}/api/4.0/queries/run/sql"
        try:
            response = requests.post(
                sql_url,
                headers={"Authorization": f"token {token}"},
                json=write_query,
                timeout=30,
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.warning(f"Failed to fetch SQL from Looker API: {e}")
            return None

    def chat(
        self,
        question: str,
        system_instruction: str = None,
        skip_agent_use: bool = False,
        agent_id: str = None,
        conversation_id: str = None,
        enable_dev_mode: bool = False,
        looker_instance_uri: str = None,
        explores: list[tuple[str, str]] = None,
        looker_golden_queries: list | dict = None,
        agent_definition: dict = None,
        thinking_mode: str = None,
    ) -> tuple[str | None, pd.DataFrame | None, dict | None, str | None, dict | None, list | None, list | None]:
        """Sends a message to a conversation and returns the generated SQL, DataFrame, query, text, and chart."""
        if enable_dev_mode and not self.looker_access_token and looker_instance_uri:
            self.exchange_credentials_for_token(looker_instance_uri)

        messages = [
            geminidataanalytics.Message(
                user_message=geminidataanalytics.UserMessage(text=question)
            )
        ]

        request_kwargs = {
            "parent": f"projects/{self.project_id}/locations/{self.location}",
            "messages": messages,
        }
        if self.credentials:
            request_kwargs["credentials"] = self.credentials
        if enable_dev_mode:
            request_kwargs["looker_settings"] = geminidataanalytics.LookerSettings(
                enable_dev_mode=True
            )
        if thinking_mode:
            mode_key = thinking_mode.strip().upper()
            try:
                request_kwargs["thinking_mode"] = getattr(
                    geminidataanalytics.ChatRequest.ThinkingMode, mode_key
                )
            except AttributeError as exc:
                valid_modes = [
                    e.name
                    for e in geminidataanalytics.ChatRequest.ThinkingMode
                    if e.name != "THINKING_MODE_UNSPECIFIED"
                ]
                raise ValueError(
                    f"Invalid thinking_mode '{thinking_mode}'. Expected one of: {', '.join(valid_modes)}"
                ) from exc

        if skip_agent_use:
            request_kwargs["inline_context"] = self._build_context(
                system_instruction=system_instruction,
                looker_instance_uri=looker_instance_uri,
                explores=explores,
                looker_golden_queries=looker_golden_queries,
                agent_definition=agent_definition,
            )
        else:
            conversation_reference = geminidataanalytics.ConversationReference(
                conversation=f"projects/{self.project_id}/locations/{self.location}/conversations/{conversation_id}",
                data_agent_context=geminidataanalytics.DataAgentContext(
                    data_agent=f"projects/{self.project_id}/locations/{self.location}/dataAgents/{agent_id}",
                ),
            )
            request_kwargs["conversation_reference"] = conversation_reference

        request = geminidataanalytics.ChatRequest(**request_kwargs)

        log_request = copy.deepcopy(request)
        if log_request.credentials and log_request.credentials.oauth:
            if log_request.credentials.oauth.secret and (
                log_request.credentials.oauth.secret.client_id
                or log_request.credentials.oauth.secret.client_secret
            ):
                log_request.credentials.oauth.secret.client_id = "[MASKED]"
                log_request.credentials.oauth.secret.client_secret = "[MASKED]"
            if log_request.credentials.oauth.token and log_request.credentials.oauth.token.access_token:
                log_request.credentials.oauth.token.access_token = "[MASKED]"
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

        for response in stream:
            if response.system_message:
                system_message = response.system_message
                data_message = response.system_message.data
                text_message = response.system_message.text
                # TODO: add python analysis
                analysis_message = response.system_message.analysis

                if "generated_sql" in data_message:
                    logger.debug(response)
                    if generated_sql is None:
                        generated_sql = ""
                    generated_sql += data_message.generated_sql
                if "query" in data_message and "looker" in data_message.query:
                    logger.debug(response)
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
                        el_dict = self._value_to_dict(el)
                        row = {
                            field: (
                                el_dict.get(field)
                                if isinstance(el_dict, dict)
                                else getattr(
                                    el,
                                    field,
                                    el[field] if hasattr(el, "__getitem__") else None,
                                )
                            )
                            for field in fields
                        }
                        data_rows.append(row)
                if text_message and text_message.parts:
                    logger.debug(response)
                    if text_message.text_type in (
                        geminidataanalytics.TextMessage.TextType.FINAL_RESPONSE,
                        geminidataanalytics.TextMessage.TextType.TEXT_TYPE_UNSPECIFIED,
                    ):
                        if generated_text is None:
                            generated_text = ""
                        generated_text += "".join(text_message.parts)
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

        if not generated_sql and generated_looker_query:
            generated_sql = self.fetch_looker_sql(
                looker_query=generated_looker_query,
                looker_instance_uri=looker_instance_uri,
                explores=explores,
                agent_definition=agent_definition,
            )

        return (
            generated_sql,
            generated_df,
            generated_looker_query,
            generated_text,
            generated_chart,
            dimensions,
            measures,
        )
