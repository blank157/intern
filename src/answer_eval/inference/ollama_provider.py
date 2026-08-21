"""OllamaProvider: communicates with Ollama via OpenAI-compatible /v1 API."""

import asyncio
import base64
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from answer_eval.core.config import load_settings
from answer_eval.core.errors import (
    InferenceError,
    InferenceOutputValidationError,
    InferenceTimeoutError,
    ModelNotFoundError,
    OllamaNotAvailableError,
    VisionRequestError,
)
from answer_eval.core.logging import get_logger
from answer_eval.hardware.detector import detect_gpus
from answer_eval.hardware.profiles import HardwareProfile
from answer_eval.inference.provider import InferenceProvider
from answer_eval.inference.types import (
    ImageInput,
    InferenceRequest,
    InferenceResponse,
    InferenceTiming,
    MemorySnapshot,
    TokenUsage,
)
from answer_eval.models.profiles import ModelCapabilities, ModelProfile
from answer_eval.runtime.profiles import RuntimeConfig

logger = get_logger("inference.ollama")


def _get_current_memory() -> MemorySnapshot:
    """Collect current VRAM and RAM snapshot."""
    import psutil

    vmem = psutil.virtual_memory()
    ram_used = round((vmem.total - vmem.available) / (1024**3), 2)
    ram_avail = round(vmem.available / (1024**3), 2)

    vram_used = 0.0
    vram_free = 0.0
    gpus = detect_gpus()
    if gpus:
        vram_used = gpus[0].vram_used_gb
        vram_free = gpus[0].vram_free_gb

    return MemorySnapshot(
        vram_used_gb=vram_used,
        vram_free_gb=vram_free,
        ram_used_gb=ram_used,
        ram_available_gb=ram_avail,
    )


def _encode_image_to_data_uri(img: ImageInput) -> str:
    """Encode ImageInput to data URI string for OpenAI-compatible vision payload."""
    raw_bytes: bytes | None = img.image_bytes
    if raw_bytes is None and img.image_path:
        p = Path(img.image_path)
        if p.exists() and p.is_file():
            with open(p, "rb") as f:
                raw_bytes = f.read()

    if not raw_bytes:
        raise VisionRequestError(
            "ImageInput has neither valid bytes nor an accessible file path.",
            details={"image_path": img.image_path},
        )

    # Normalize mime type
    mime = img.mime_type or "image/png"
    if img.image_path:
        ext = Path(img.image_path).suffix.lower()
        if ext in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif ext == ".webp":
            mime = "image/webp"
        elif ext == ".png":
            mime = "image/png"

    encoded = base64.b64encode(raw_bytes).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


class OllamaProvider(InferenceProvider):
    """
    Inference provider communicating with Ollama via standard OpenAI-compatible API.
    Supports vision, strict OCR, structured JSON output, configurable timeouts and retries.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        api_key: str = "ollama",
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        settings = load_settings()
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or settings.ollama.base_url).rstrip("/")
        self.model_name = model_name or os.getenv("VISION_MODEL") or settings.ollama.model
        self.api_key = api_key or os.getenv("OLLAMA_API_KEY") or settings.ollama.api_key
        self.timeout_seconds = float(
            os.getenv("OLLAMA_TIMEOUT", str(timeout_seconds or settings.ollama.timeout_seconds))
        )
        self.max_retries = int(os.getenv("OLLAMA_MAX_RETRIES", str(max_retries or settings.ollama.max_retries)))

        self.model_profile: ModelProfile | None = None
        self.runtime_config: RuntimeConfig | None = None
        self.hardware_profile: HardwareProfile | None = None
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Create or reuse httpx.AsyncClient."""
        if self._client is None or self._client.is_closed:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout_seconds, connect=10.0),
            )
        return self._client

    async def initialize(
        self,
        model: ModelProfile,
        config: RuntimeConfig,
        hardware: HardwareProfile | None = None,
    ) -> None:
        """Initialize provider with model and runtime configuration."""
        self.model_profile = model
        self.runtime_config = config
        self.hardware_profile = hardware
        if model.display_name and ":" in model.model_id:
            self.model_name = model.model_id

        logger.info(
            "Initialized OllamaProvider",
            base_url=self.base_url,
            model_name=self.model_name,
            timeout_seconds=self.timeout_seconds,
        )

    async def health_check(self) -> bool:
        """Verify Ollama is reachable and ready."""
        status = await self.check_detailed_health()
        return status.get("available", False)

    async def check_detailed_health(self) -> dict[str, Any]:
        """
        Perform a comprehensive health and model availability check.
        Returns a structured result dict.
        """
        client = self._get_client()
        result: dict[str, Any] = {
            "available": False,
            "provider": "ollama",
            "model": self.model_name,
            "base_url": self.base_url,
            "installed_models": [],
            "error": None,
            "help_message": None,
        }

        try:
            # Query /models endpoint (OpenAI compatible)
            resp = await client.get("/models")
            if resp.status_code == 200:
                data = resp.json()
                models_list = [m.get("id", "") for m in data.get("data", [])]
                result["installed_models"] = models_list

                # Check if configured model exists (exact match or latest alias)
                matched = any(
                    self.model_name == m or self.model_name == f"{m}:latest" or m == f"{self.model_name}:latest"
                    for m in models_list
                )

                if matched or not models_list:
                    # If models list returned the model or if list is empty (direct forward)
                    result["available"] = True
                else:
                    result["available"] = False
                    result["error"] = f"Configured model '{self.model_name}' is not installed in Ollama."
                    result["help_message"] = f"Install it using: ollama pull {self.model_name}"
            else:
                result["error"] = f"Ollama returned HTTP {resp.status_code}: {resp.text}"
                result["help_message"] = "Ensure Ollama is running using: ollama serve"

        except httpx.ConnectError:
            result["error"] = f"Ollama is not reachable at {self.base_url}."
            result["help_message"] = "Ollama is not running. Start it using: ollama serve"
        except httpx.TimeoutException:
            result["error"] = f"Connection to Ollama at {self.base_url} timed out."
            result["help_message"] = "Check server load or verify base_url."
        except Exception as e:
            result["error"] = f"Unexpected health check failure: {e}"

        return result

    async def verify_model_available(self) -> None:
        """Verify model presence, raising clean descriptive exceptions if missing."""
        health = await self.check_detailed_health()
        if not health["available"]:
            if (
                "not running" in (health.get("help_message") or "").lower()
                or "not reachable" in (health.get("error") or "").lower()
            ):
                raise OllamaNotAvailableError(
                    f"Ollama is not running at {self.base_url}.\nStart it using: ollama serve",
                    details=health,
                )
            raise ModelNotFoundError(
                f"Configured vision model '{self.model_name}' was not found in Ollama.\nInstall it using: ollama pull {self.model_name}",
                details=health,
            )

    def get_capabilities(self) -> ModelCapabilities:
        """Return capabilities for active Ollama model."""
        if self.model_profile:
            return self.model_profile.to_capabilities()
        return ModelCapabilities(
            vision=True,
            structured_output=True,
            thinking=False,
            max_context=8192,
        )

    def get_memory_usage(self) -> MemorySnapshot:
        """Return memory utilization snapshot."""
        return _get_current_memory()

    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        """
        Execute text or vision inference request against Ollama OpenAI-compatible API.
        Includes automatic transient retries and timing/memory metadata.
        """
        client = self._get_client()
        t_start = time.perf_counter()

        # Build messages payload
        messages = self._build_chat_messages(request)
        model_to_use = self.model_name

        payload: dict[str, Any] = {
            "model": model_to_use,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
            "stream": False,
            "options": {
                "num_ctx": 16384,
                "num_predict": request.max_tokens or 4096,
                "temperature": request.temperature,
            },
        }

        # Safe logging without private image data
        image_count = len(request.images)
        logger.info(
            "Executing Ollama inference request",
            request_id=request.request_id,
            model=model_to_use,
            images_count=image_count,
            prompt_preview=request.prompt[:60] if request.prompt else "",
        )

        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            try:
                resp = await client.post("/chat/completions", json=payload)

                if resp.status_code == 200:
                    data = resp.json()
                    t_end = time.perf_counter()
                    dur_ms = round((t_end - t_start) * 1000, 2)

                    choices = data.get("choices", [])
                    if not choices:
                        raise InferenceError("Ollama response contained no completion choices.")

                    text_content = choices[0].get("message", {}).get("content", "")

                    usage_data = data.get("usage", {})
                    prompt_tokens = usage_data.get("prompt_tokens", 0)
                    completion_tokens = usage_data.get("completion_tokens", 0)
                    total_tokens = usage_data.get("total_tokens", prompt_tokens + completion_tokens)
                    tps = round(completion_tokens / (dur_ms / 1000), 2) if dur_ms > 0 else 0.0

                    logger.info(
                        "Ollama inference completed",
                        request_id=request.request_id,
                        duration_ms=dur_ms,
                        completion_tokens=completion_tokens,
                        tokens_per_second=tps,
                    )

                    return InferenceResponse(
                        request_id=request.request_id,
                        provider="ollama",
                        model_id=model_to_use,
                        quantization=self.model_profile.quantization if self.model_profile else "auto",
                        text=text_content,
                        usage=TokenUsage(
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            total_tokens=total_tokens,
                        ),
                        timing=InferenceTiming(
                            total_inference_ms=dur_ms,
                            tokens_per_second=tps,
                        ),
                        memory=self.get_memory_usage(),
                    )

                elif resp.status_code == 404:
                    raise ModelNotFoundError(
                        f"Model '{model_to_use}' not found on Ollama server. Pull it using: ollama pull {model_to_use}",
                        details={"status_code": 404, "response": resp.text},
                    )
                elif resp.status_code in (500, 502, 503, 504):
                    logger.warning(
                        "Transient Ollama server error",
                        attempt=attempt,
                        status_code=resp.status_code,
                        response=resp.text,
                    )
                    last_err = InferenceError(f"Ollama server error HTTP {resp.status_code}: {resp.text}")
                else:
                    raise InferenceError(
                        f"Ollama request failed with HTTP {resp.status_code}: {resp.text}",
                        details={"status_code": resp.status_code},
                    )

            except httpx.ConnectError as e:
                logger.warning("Connection error reaching Ollama", attempt=attempt, error=str(e))
                last_err = OllamaNotAvailableError(
                    f"Ollama server is not reachable at {self.base_url}. Start it with: ollama serve",
                    details={"base_url": self.base_url},
                )
            except httpx.TimeoutException:
                logger.warning("Ollama request timed out", attempt=attempt, timeout=self.timeout_seconds)
                last_err = InferenceTimeoutError(
                    f"Ollama inference timed out after {self.timeout_seconds}s.",
                    details={"timeout_seconds": self.timeout_seconds},
                )
            except Exception as e:
                if isinstance(e, (ModelNotFoundError, OllamaNotAvailableError, InferenceError)):
                    raise
                logger.warning("Unexpected error during Ollama inference", attempt=attempt, error=str(e))
                last_err = e

            if attempt <= self.max_retries:
                backoff = 1.0 * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)

        if last_err:
            raise last_err
        raise InferenceError("Ollama inference failed after maximum retries.")

    async def infer_structured(
        self,
        request: InferenceRequest,
        schema: type | dict[str, Any],
        max_retries: int = 2,
    ) -> InferenceResponse:
        """
        Execute inference and validate JSON output schema with controlled repair retries.

        Attempt 0: Full schema-constrained prompt, try to parse output.
        Attempt 1+: Feed validation error back to the model with explicit repair instructions.

        Handles:
          - Raw JSON responses
          - Markdown-fenced responses (```json ... ```)
          - JSON embedded inside surrounding prose (extracted via brace matching)
        """
        req_copy = request.model_copy(deep=True)
        schema_desc = (
            schema
            if isinstance(schema, dict)
            else schema.model_json_schema()
            if hasattr(schema, "model_json_schema")
            else str(schema)
        )

        # Build initial prompt with schema instruction appended
        schema_instruction = (
            f"\n\nYou MUST respond with ONLY a valid JSON object matching this schema "
            f"(no markdown fences, no explanation):\n{json.dumps(schema_desc, indent=2)}"
        )
        req_copy.prompt = request.prompt + schema_instruction

        last_error_text = ""
        last_raw: str = ""

        for attempt in range(max_retries + 1):
            if attempt > 0:
                # Repair prompt: show model exactly what went wrong
                repair_note = (
                    f"\n\nYour previous response did not contain valid JSON.\n"
                    f"Validation error: {last_error_text[:300]}\n\n"
                    f"Rules:\n"
                    f"- Return ONLY the JSON object.\n"
                    f"- No markdown code fences (no ```json).\n"
                    f"- No explanation before or after the JSON.\n"
                    f"- Must match this schema exactly:\n"
                    f"{json.dumps(schema_desc, indent=2)}"
                )
                req_copy.prompt = request.prompt + repair_note
                logger.info(
                    "Structured JSON repair retry",
                    attempt=attempt,
                    max_retries=max_retries,
                    validation_error=last_error_text[:200],
                    request_id=request.request_id,
                )

            resp = await self.infer(req_copy)
            raw = resp.text.strip()
            last_raw = raw

            cleaned = self._extract_json_from_response(raw)

            try:
                data = json.loads(cleaned)
                if isinstance(schema, type) and issubclass(schema, BaseModel):
                    validated = schema.model_validate(data)
                    resp.structured_data = validated.model_dump()
                else:
                    resp.structured_data = data
                return resp
            except (json.JSONDecodeError, ValidationError) as e:
                last_error_text = str(e)
                logger.warning(
                    "Structured JSON validation failed",
                    attempt=attempt,
                    raw_response_length=len(raw),
                    raw_preview=raw[:120],
                    validation_error=last_error_text[:200],
                    request_id=request.request_id,
                )

        raise InferenceOutputValidationError(
            f"Failed to obtain valid structured JSON from Ollama after {max_retries} retries.",
            details={
                "last_error": last_error_text,
                "raw_response_length": len(last_raw),
                "raw_response_preview": last_raw[:300],
            },
        )

    def _extract_json_from_response(self, text: str) -> str:
        """
        Extract clean JSON string from raw model response.
        Handles markdown fences, leading/trailing whitespace, and embedded JSON in prose.
        """
        cleaned = text.strip()

        # 1. Strip markdown fences if present
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # 2. If it already parses or starts with { / [, return it
        if cleaned.startswith("{") or cleaned.startswith("["):
            return cleaned

        # 3. Search for first { and matching last }
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return cleaned[first_brace : last_brace + 1]

        # 4. Search for first [ and matching last ]
        first_bracket = cleaned.find("[")
        last_bracket = cleaned.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            return cleaned[first_bracket : last_bracket + 1]

        return cleaned

    def _build_chat_messages(self, request: InferenceRequest) -> list[dict[str, Any]]:
        """Construct OpenAI-compatible chat messages array for vision/text."""
        if not request.images:
            return [{"role": "user", "content": request.prompt}]

        content_parts: list[dict[str, Any]] = []

        # Add image parts
        for img in request.images:
            data_uri = _encode_image_to_data_uri(img)
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": data_uri},
                }
            )

        # Add text prompt
        content_parts.append(
            {
                "type": "text",
                "text": request.prompt,
            }
        )

        return [{"role": "user", "content": content_parts}]

    async def shutdown(self) -> None:
        """Close HTTP client connection pool."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("OllamaProvider client connection closed.")
