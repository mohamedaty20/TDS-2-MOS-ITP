"""
services/ai_service.py — Thin wrapper around google-genai with retry.
"""
import asyncio
from google.genai import types
from config import client, GEMINI_MODEL


async def _one_attempt(contents, temperature, timeout, max_tokens=None):
    cfg_kwargs = {"temperature": temperature}
    if max_tokens is not None:
        try:
            cfg_kwargs["max_output_tokens"] = int(max_tokens)
        except Exception:
            pass
    config = types.GenerateContentConfig(**cfg_kwargs)

    async def _call():
        return await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=config,
        )
    return await asyncio.wait_for(_call(), timeout=timeout)


async def call_gemini_json(contents, temperature=0.0, timeout=45,
                            max_tokens=None):
    if not client:
        raise Exception("GEMINI_API_KEY missing.")

    last_err = None
    for attempt in range(1, 4):
        try:
            response = await _one_attempt(contents, temperature, timeout,
                                            max_tokens=max_tokens)
            txt = response.text or ""
            return txt
        except asyncio.TimeoutError:
            last_err = "AI request timed out after " + str(timeout) + "s."
        except Exception as e:
            msg = str(e)
            last_err = msg
            retryable = ("503" in msg or "UNAVAILABLE" in msg or
                         "high demand" in msg or "overloaded" in msg)
            if not retryable:
                raise Exception("AI request failed: " + msg)
        if attempt < 3:
            await asyncio.sleep(2 * attempt)

    raise Exception("AI request failed after retries: " + str(last_err))
