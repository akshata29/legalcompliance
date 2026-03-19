"""
Central configuration — loads all environment variables and provides
typed settings for every service in the application.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from azure.identity import ClientSecretCredential, DefaultAzureCredential
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "..", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Azure AD ────────────────────────────────────────────────────────────
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str
    azure_subscription_id: str

    # ── Azure AI Foundry ────────────────────────────────────────────────────
    foundry_project_endpoint: str
    foundry_model_deployment_name: str = "chat4o"
    foundry_agent_name: str = "legalcompliance"
    foundry_api_version: str = "2025-05-15-preview"
    foundry_response_timeout_seconds: int = 180

    # ── Azure OpenAI ────────────────────────────────────────────────────────
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment_name: str = "chat4o"
    azure_openai_embedding_deployment_name: str = "embedding"

    # Models to use per phase (can be overridden via env)
    categorization_model: str = "chat4o"        # Use gpt-4o-mini equivalent
    extraction_model: str = "chat4o"            # gpt-4o
    analysis_model: str = "chat4o"              # gpt-4o

    # ── Azure AI Search ─────────────────────────────────────────────────────
    search_endpoint: str
    search_index: str = "legalcompliance"
    search_api_key_secret_name: str = ""

    # ── Document Intelligence ───────────────────────────────────────────────
    document_intelligence_endpoint: str
    document_intelligence_api_key: str

    # ── Content Understanding ───────────────────────────────────────────────
    content_understanding_endpoint: str
    content_understanding_api_version: str = "2025-11-01"
    content_understanding_api_key: Optional[str] = None
    content_understanding_completion_model: str = "gpt-4.1"

    # ── Azure Blob Storage ──────────────────────────────────────────────────
    azure_storage_connection_string: Optional[str] = None   # kept for reference; auth uses azure_credential
    azure_blob_storage_name: str
    azure_storage_container: str = "portfolio"

    # ── CosmosDB ────────────────────────────────────────────────────────────
    cosmosdb_endpoint: str
    cosmos_db_database: str = "compexdocs"
    cosmos_db_container: str = "legal"

    # ── Bing Grounding ──────────────────────────────────────────────────────
    bing_grounding_connection_id: str = ""
    bing_grounding_connection_name: str = ""

    # ── CORS ─────────────────────────────────────────────────────────────────
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # ── Pipeline tuning ─────────────────────────────────────────────────────
    legacy_max_workers: int = 5                  # ThreadPoolExecutor workers
    optimized_batch_size: int = 10               # Provisions per LLM call
    optimized_semaphore_limit: int = 15          # Max concurrent async calls (categorize)
    optimized_semaphore_extract: int = 10        # Max concurrent extraction calls (Phase B)
    optimized_semaphore_analyze: int = 15        # Max concurrent analysis calls (Phase C)
    optimized_max_tokens_categorize: int = 300
    optimized_max_tokens_extract: int = 800
    optimized_max_tokens_analyze: int = 1200

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def azure_credential(self):
        """Service-principal credential (preferred) or DefaultAzureCredential."""
        if self.azure_client_id and self.azure_client_secret and self.azure_tenant_id:
            return ClientSecretCredential(
                tenant_id=self.azure_tenant_id,
                client_id=self.azure_client_id,
                client_secret=self.azure_client_secret,
            )
        return DefaultAzureCredential()


@lru_cache
def get_settings() -> Settings:
    return Settings()
