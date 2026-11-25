"""Bounded Groq requests and process-wide token pacing for the single-worker backend."""
import logging
import time
from collections import deque
from dataclasses import dataclass
from threading import Lock

from .config import settings
from .errors import PipelineError

logger = logging.getLogger(__name__)


def token_bound(text: str) -> int:
    # UTF-8 bytes are a deliberately conservative bound for byte-level tokenizers.
    # No tokenizer downloads or approximate chars/4 estimates are required.
    return len(text.encode("utf-8"))


@dataclass
class Reservation:
    expires_at: float
    tokens: int


class TokenPacer:
    def __init__(self, clock=time.monotonic, sleep=time.sleep):
        self.clock = clock
        self.sleep = sleep
        self.lock = Lock()
        self.reservations: deque[Reservation] = deque()

    def reserve(self, tokens: int) -> Reservation:
        if tokens > settings.groq_tpm_limit:
            raise PipelineError("The model request exceeds GROQ_TPM_LIMIT. Reduce the LLM budgets.")
        while True:
            with self.lock:
                now = self.clock()
                while self.reservations and self.reservations[0].expires_at <= now:
                    self.reservations.popleft()
                if sum(item.tokens for item in self.reservations) + tokens <= settings.groq_tpm_limit:
                    reservation = Reservation(now + 61, tokens)
                    self.reservations.append(reservation)
                    return reservation
                delay = max(0.01, self.reservations[0].expires_at - now)
            logger.info("Waiting %.1fs for the Groq token budget", delay)
            self.sleep(min(delay, 30))

    def complete(self, reservation: Reservation, actual_tokens: int | None) -> None:
        with self.lock:
            # Keep the reservation until 61s after completion; concurrent requests
            # cannot spend tokens while this request is still running.
            reservation.expires_at = self.clock() + 61
            if actual_tokens is not None:
                reservation.tokens = max(0, actual_tokens)
            self.reservations = deque(sorted(self.reservations, key=lambda item: item.expires_at))


pacer = TokenPacer()


def generate_text(prompt: str, *, model: str, stage: str, json_mode: bool = False) -> str:
    from groq import Groq

    if not settings.groq_api_key:
        raise PipelineError("GROQ_API_KEY is missing. Configure it and recreate the backend container.")
    estimated_input = token_bound(prompt) + 128
    if estimated_input > settings.llm_input_budget:
        raise PipelineError(f"{stage} input exceeds LLM_INPUT_BUDGET. Reduce the evidence batch size.")
    request_tokens = estimated_input + settings.llm_output_budget + 128
    logger.info("%s request model=%s input_bound=%s output_limit=%s", stage, model,
                estimated_input, settings.llm_output_budget)
    params = {
        "model": model, "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": settings.llm_output_budget, "temperature": 0,
    }
    if json_mode:
        params["response_format"] = {"type": "json_object"}
    if model.startswith("openai/gpt-oss-"):
        params["reasoning_effort"] = "low"

    # No automatic SDK retries: deterministic auth/model/size errors must stop,
    # and temporary rate limits get one paced retry here.
    client = Groq(api_key=settings.groq_api_key, max_retries=0, timeout=60)
    try:
        for attempt in range(2):
            reservation = pacer.reserve(request_tokens)
            try:
                response = client.chat.completions.create(**params)
            except Exception as error:
                status = getattr(error, "status_code", None)
                pacer.complete(reservation, 0 if status in (400, 401, 403, 404, 413, 429) else None)
                if status == 429 and attempt == 0:
                    headers = getattr(getattr(error, "response", None), "headers", {})
                    try:
                        delay = float(headers.get("retry-after", "60"))
                    except (TypeError, ValueError):
                        delay = 60
                    if delay > 60:
                        raise PipelineError("Groq rate limit reached. Wait before submitting another request.") from error
                    logger.warning("Groq rate limit during %s; retrying once after %.1fs", stage, delay)
                    time.sleep(max(1, delay))
                    continue
                if status in (401, 403):
                    message = "Groq rejected the API key or access. Check GROQ_API_KEY and account permissions."
                elif status == 404:
                    message = f"Groq model '{model}' is unavailable. Check {stage.upper()}_MODEL or GROQ_MODEL."
                elif status == 413:
                    message = "Groq rejected the request size. Lower LLM_INPUT_BUDGET or check GROQ_TPM_LIMIT."
                elif status == 429:
                    message = "Groq rate limit reached. Wait before submitting another request."
                else:
                    message = f"{stage} could not complete its Groq request. Check server logs and retry."
                logger.error("%s Groq request failed status=%s type=%s", stage, status, type(error).__name__)
                raise PipelineError(message) from error

            usage = getattr(response, "usage", None)
            pacer.complete(reservation, usage.total_tokens if usage is not None else None)
            choice = response.choices[0]
            if choice.finish_reason == "length":
                raise PipelineError(f"{stage} response was truncated. Increase LLM_OUTPUT_BUDGET or use smaller batches.")
            text = (choice.message.content or "").strip()
            if not text:
                raise PipelineError(f"{stage} returned an empty response. Try a larger output budget or another model.")
            return text
    finally:
        client.close()
