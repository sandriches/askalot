"""Factories for external service clients."""

from functools import lru_cache

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI

from rag.config import get_settings

# Entra ID scope for all Azure AI services (OpenAI, Document Intelligence, ...).
COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"


@lru_cache
def get_openai_client() -> OpenAI:
    """OpenAI SDK client pointed at our Azure resource.

    Auth: an API key if one is configured, otherwise Entra ID. With Entra ID,
    `DefaultAzureCredential` picks up `az login` on a laptop and a managed
    identity in Azure, so the same code runs in both places without secrets.
    The token provider is a callable; the SDK calls it per request and it
    refreshes tokens before they expire.
    """
    settings = get_settings()
    if settings.azure_openai_api_key:
        api_key = settings.azure_openai_api_key.get_secret_value()
    else:
        api_key = get_bearer_token_provider(DefaultAzureCredential(), COGNITIVE_SERVICES_SCOPE)
    return OpenAI(base_url=settings.openai_base_url, api_key=api_key)


@lru_cache
def get_docintel_client() -> DocumentIntelligenceClient:
    """Document Intelligence client, authenticated with Entra ID.

    Needs the 'Cognitive Services User' role on the resource; the OpenAI role
    doesn't include Document Intelligence's analyze action.
    """
    endpoint = get_settings().azure_docintel_endpoint
    if not endpoint:
        raise RuntimeError("AZURE_DOCINTEL_ENDPOINT is not set")
    return DocumentIntelligenceClient(endpoint, DefaultAzureCredential())
