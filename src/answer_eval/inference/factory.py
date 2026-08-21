"""Inference provider factory."""

from answer_eval.core.errors import ConfigurationError
from answer_eval.inference.llama_server_provider import LlamaServerProvider
from answer_eval.inference.ollama_provider import OllamaProvider
from answer_eval.inference.provider import InferenceProvider
from answer_eval.inference.vllm_provider import VLLMProvider
from answer_eval.models.profiles import ModelProfile, ProviderType


def create_inference_provider(model: ModelProfile | None = None) -> InferenceProvider:
    """Instantiate appropriate InferenceProvider based on model profile or default settings."""
    if model is None:
        return OllamaProvider()

    if model.provider_type == ProviderType.OLLAMA:
        return OllamaProvider(
            base_url=model.endpoint,
            model_name=model.model_id if ":" in model.model_id else None,
        )
    elif model.provider_type == ProviderType.LLAMA_SERVER:
        return LlamaServerProvider(base_url=model.endpoint)
    elif model.provider_type == ProviderType.VLLM:
        return VLLMProvider(base_url=model.endpoint or "http://localhost:8000/v1")
    else:
        raise ConfigurationError(
            f"Unsupported provider type: '{model.provider_type}'",
            details={"model_id": model.model_id},
        )
