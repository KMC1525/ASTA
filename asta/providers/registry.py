"""Catálogo de provedores e fábrica."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .anthropic import AnthropicProvider
from .base import Provider, ProviderError
from .demo import DemoProvider
from .local_llama import LocalLlamaProvider
from .openai_compat import OpenAICompatProvider

# kind: demo | anthropic | openai | local_hf
PRESETS: Dict[str, Dict[str, Any]] = {
    "demo": {
        "label": "Demo (offline, sem IA)", "kind": "demo", "local": True, "needs_key": False, "vision": False,
        "hint": "Gerador de regras para testar tudo sem chave e sem internet.",
    },
    "anthropic": {
        "label": "Claude (Anthropic)", "kind": "anthropic", "base_url": "https://api.anthropic.com",
        "model": "claude-sonnet-5-5", "needs_key": True, "vision": True,
        "docs": "https://console.anthropic.com/settings/keys",
    },
    "openai": {
        "label": "ChatGPT (OpenAI)", "kind": "openai", "base_url": "https://api.openai.com/v1",
        "model": "", "needs_key": True, "vision": True, "json": True,
        "docs": "https://platform.openai.com/api-keys",
    },
    "xai": {
        "label": "Grok (xAI)", "kind": "openai", "base_url": "https://api.x.ai/v1",
        "model": "", "needs_key": True, "vision": True, "json": True,
        "docs": "https://console.x.ai",
    },
    "google": {
        "label": "Gemini (Google)", "kind": "openai", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "", "needs_key": True, "vision": True,
        "docs": "https://aistudio.google.com/apikey",
    },
    "openrouter": {
        "label": "OpenRouter (centenas de modelos)", "kind": "openai", "base_url": "https://openrouter.ai/api/v1",
        "model": "", "needs_key": True, "vision": True,
        "docs": "https://openrouter.ai/keys",
    },
    "huggingface": {
        "label": "Hugging Face (Inference)", "kind": "openai", "base_url": "https://router.huggingface.co/v1",
        "model": "", "needs_key": True, "vision": False,
        "docs": "https://huggingface.co/settings/tokens",
    },
    "ollama": {
        "label": "Ollama (local)", "kind": "openai", "base_url": "http://127.0.0.1:11434/v1",
        "model": "", "needs_key": False, "local": True, "vision": False,
        "docs": "https://ollama.com/download",
    },
    "lmstudio": {
        "label": "LM Studio (local)", "kind": "openai", "base_url": "http://127.0.0.1:1234/v1",
        "model": "", "needs_key": False, "local": True, "vision": False,
        "docs": "https://lmstudio.ai",
    },
    "llamacpp": {
        "label": "llama.cpp server (local)", "kind": "openai", "base_url": "http://127.0.0.1:8080/v1",
        "model": "", "needs_key": False, "local": True, "vision": False,
        "docs": "https://github.com/ggml-org/llama.cpp",
    },
    "local_hf": {
        "label": "Hugging Face GGUF (embutido)", "kind": "local_hf", "model": "", "needs_key": False,
        "local": True, "vision": False,
        "hint": 'Roda dentro do ASTA. Requer:  pip install "asta[local]"',
    },
    "custom": {
        "label": "OpenAI-compatível (personalizado)", "kind": "openai", "base_url": "",
        "model": "", "needs_key": False, "vision": False,
    },
}


def provider_config(settings: Dict[str, Any], pid: str) -> Dict[str, Any]:
    preset = PRESETS.get(pid)
    if not preset:
        raise ProviderError(f"Provedor desconhecido: {pid}")
    cfg = dict(preset)
    user = (settings.get("providers") or {}).get(pid, {})
    for key in ("base_url", "api_key", "model", "vision", "n_ctx"):
        if key in user and user[key] not in (None, ""):
            cfg[key] = user[key]
    if pid == "huggingface" and not cfg.get("api_key"):
        cfg["api_key"] = (settings.get("hf") or {}).get("token", "")
    cfg["id"] = pid
    return cfg


def build_provider(settings: Dict[str, Any], pid: str, models_dir: Optional[Path] = None) -> Provider:
    cfg = provider_config(settings, pid)
    kind = cfg["kind"]
    if kind == "demo":
        return DemoProvider(cfg)
    if kind == "anthropic":
        return AnthropicProvider(cfg)
    if kind == "local_hf":
        cfg["models_dir"] = str(models_dir or ".")
        return LocalLlamaProvider(cfg)
    return OpenAICompatProvider(cfg)


def describe_presets() -> List[Dict[str, Any]]:
    out = []
    for pid, p in PRESETS.items():
        out.append({
            "id": pid, "label": p["label"], "kind": p["kind"], "base_url": p.get("base_url", ""),
            "model": p.get("model", ""), "needs_key": p.get("needs_key", False), "local": p.get("local", False),
            "vision": p.get("vision", False), "docs": p.get("docs", ""), "hint": p.get("hint", ""),
        })
    return out
