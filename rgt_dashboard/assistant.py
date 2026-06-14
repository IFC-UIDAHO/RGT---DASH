# -*- coding: utf-8 -*-
"""
ForestTask -- MindRouter-backed report assistant.

One branded assistant; best model auto-selected per request.
reasoning_effort=maximum for all calls. max_tokens from config.
"""
from __future__ import annotations

import json
import logging

import requests

from .config import MindRouter

logger = logging.getLogger("rgt.assistant")

SYSTEM_PROMPT = (
    "You are ForestTask, the report assistant for the Intermountain Forestry Cooperative "
    "(University of Idaho) Realized Genetic Gain Trials (RGT). The trials compare genetically "
    "Improved Douglas-fir seedlots against local Woods Run (unimproved) checks across "
    "installations in two regions: the Inland Northwest (INW) and the Klamath-Siskiyou (K-S), over "
    "three measurement years and three growth metrics (caliper, height, volume).\n"
    "Use ONLY these region names: INW = Inland Northwest, K-S = Klamath-Siskiyou. Never use any other.\n\n"
    "DEFINITIONS:\n"
    "- Realized genetic gain (%) = (Improved mean minus Woods Run mean) / Woods Run mean x 100, "
    "for an installation/year/metric (White, Adams & Neale 2007, Forest Genetics, CABI).\n"
    "- Significance: Welch t-test on seedlot (genetic-entry) means; p<0.05 significant. "
    "Stars * p<0.05, ** p<0.01, *** p<0.001.\n"
    "- Gain vs site productivity: Pearson r between Woods Run site mean (productivity proxy) "
    "and realized gain %. Negative r = gains larger on poorer sites (G x E, Stonecypher 1996).\n"
    "- Negative gain = Improved under-performed the local check. CORE = main sites; "
    "TRANSFER = off-site climate-transfer tests.\n\n"
    "YOU RECEIVE TWO JSON CONTEXT BLOCKS each message:\n"
    "1) CURRENT_VIEW -- the exact filters the user has selected.\n"
    "2) TRIAL_OVERVIEW -- aggregate facts spanning ALL years, regions, metrics and sites.\n\n"
    "RULES:\n"
    "1. Answer ANY question using whichever block(s) apply.\n"
    "2. Ground every number in the provided context; never invent figures.\n"
    "3. OUTPUT: clean Markdown prose -- '- ' bullets for lists. No LaTeX, no images.\n"
    "4. Be concise and professional, suitable for a cooperative progress report."
)


def context_block(context: dict) -> str:
    return ("DATA CONTEXT (the only numbers you may cite -- CURRENT_VIEW is the user's current "
            "filters; TRIAL_OVERVIEW spans the whole trial):\n"
            + json.dumps(context, indent=1, default=str))


def auto_model(prompt: str) -> str:
    """Always use the large model for quality."""
    return MindRouter.LARGE_MODEL


class MindRouterClient:
    def __init__(self, base_url=None, api_key=None, timeout=None):
        self.base_url = (base_url or MindRouter.BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else MindRouter.API_KEY
        self.timeout = timeout or MindRouter.TIMEOUT

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def chat(self, messages, *, model=None, temperature=None, max_tokens=None,
             reasoning_effort=None, timeout=None) -> dict:
        if not self.configured:
            return dict(ok=False, content="", model=None, error=(
                "ForestTask is offline. Add MINDROUTER_API_KEY to the .env file and restart."))
        chosen = model or MindRouter.LARGE_MODEL
        payload = {
            "model": chosen, "messages": messages,
            "temperature": MindRouter.TEMPERATURE if temperature is None else temperature,
            "max_tokens": max_tokens or MindRouter.CHAT_MAX_TOKENS,
            "stream": False,
        }
        eff = reasoning_effort if reasoning_effort is not None else MindRouter.CHAT_REASONING
        if eff:
            payload["reasoning_effort"] = eff
        _timeout = timeout if timeout is not None else self.timeout
        try:
            r = requests.post(f"{self.base_url}/chat/completions", headers=self._headers(),
                              json=payload, timeout=_timeout)
            if r.status_code == 404 and chosen != MindRouter.FALLBACK_MODEL:
                logger.warning("Model %s unavailable (404); falling back to %s",
                               chosen, MindRouter.FALLBACK_MODEL)
                chosen = MindRouter.FALLBACK_MODEL
                payload["model"] = chosen
                r = requests.post(f"{self.base_url}/chat/completions", headers=self._headers(),
                                  json=payload, timeout=_timeout)
        except requests.exceptions.Timeout:
            return dict(ok=False, content="", model=chosen,
                        error="The model took too long to respond. Try a shorter request.")
        except requests.exceptions.RequestException as exc:
            return dict(ok=False, content="", model=chosen,
                        error=f"Could not reach MindRouter at {self.base_url}: {exc}")
        if r.status_code == 401:
            return dict(ok=False, content="", model=chosen,
                        error="MindRouter rejected the API key (401). Check MINDROUTER_API_KEY in .env.")
        if r.status_code == 429:
            return dict(ok=False, content="", model=chosen,
                        error="Quota/rate limit reached on MindRouter (429). Wait a moment and retry.")
        if r.status_code >= 500:
            return dict(ok=False, content="", model=chosen,
                        error="MindRouter's backend is busy right now (server error). "
                              "Please try again in a moment.")
        if r.status_code >= 400:
            return dict(ok=False, content="", model=chosen,
                        error=f"MindRouter error {r.status_code}: {_extract_error(r)}")
        try:
            content = r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            return dict(ok=False, content="", model=chosen,
                        error=f"Unexpected MindRouter response: {exc}")
        return dict(ok=True, content=content.strip(), model=chosen, error=None)


def _extract_error(resp) -> str:
    try:
        body = resp.json()
        if isinstance(body.get("error"), dict):
            return body["error"].get("message", str(body))
        return body.get("detail", str(body))
    except Exception:
        return resp.text[:200]


def build_messages(history, context, *, system=SYSTEM_PROMPT):
    msgs = [{"role": "system", "content": system},
            {"role": "system", "content": context_block(context)}]
    msgs.extend(history)
    return msgs


CLIENT = MindRouterClient()
