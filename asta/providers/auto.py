"""Escolha automática do provedor de IA das conversas (avatars, NPCs): sempre IA de verdade quando existe alguma disponível.

O papel «Personagens (chat e voz)» pode estar em `auto` (padrão), ou ainda no valor antigo `demo`. Nos dois casos o ASTA procura, nesta ordem:
  1. o provedor de **geração** configurado (nuvem — Anthropic, OpenAI, Gemini… — ou local — Ollama, LM Studio, llama.cpp server…), se estiver usável;
  2. um **modelo local embutido** (GGUF de texto): o escolhido em *Configuração → Provedores → Hugging Face GGUF* ou o pré-instalado, se a
     biblioteca `llama-cpp-python` estiver instalada;
  3. só se nada disso existir, o **Demo** (respostas pré-programadas, sem IA) — e a interface avisa isso e o porquê.
Um provedor escolhido explicitamente (qualquer um que não seja `auto`/`demo`) é sempre respeitado: se faltar chave ou o servidor não responder, o erro aparece.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .registry import PRESETS, build_provider, provider_config

AUTO_VALUES = ("", "auto", "demo")


def _llama_installed() -> bool:
    try:
        return importlib.util.find_spec("llama_cpp") is not None
    except (ImportError, ValueError):
        return False


def local_text_model(settings: Dict[str, Any], models_dir: Optional[Path]) -> str:
    """Nome do GGUF de texto a usar: o escolhido nas configurações (se o arquivo existe) ou o pré-instalado já baixado; "" se não há."""
    if not models_dir:
        return ""
    models_dir = Path(models_dir)
    chosen = str(((settings.get("providers") or {}).get("local_hf") or {}).get("model") or "")
    if chosen:
        path = Path(chosen)
        if (path if path.is_absolute() else models_dir / chosen).is_file():
            return chosen
    from .. import preinstalled

    for e in preinstalled.CATALOG:
        if e["kind"] == "text" and (models_dir / Path(e["file"]).name).is_file():
            return Path(e["file"]).name
    return ""


def usable(settings: Dict[str, Any], pid: str, models_dir: Optional[Path]) -> bool:
    """O provedor tem o que precisa para responder (chave, modelo, biblioteca/arquivo)? O Demo conta como "não": não é IA."""
    if pid not in PRESETS:
        return False
    cfg = provider_config(settings, pid)
    if cfg["kind"] == "demo":
        return False
    if cfg["kind"] == "local_hf":
        return bool(local_text_model(settings, models_dir)) and _llama_installed()
    if cfg.get("needs_key"):
        return bool(cfg.get("api_key"))
    # servidor local/OpenAI-compatível sem chave (Ollama, LM Studio, llama.cpp server, personalizado): precisa do modelo (e do endereço, no personalizado)
    return bool(cfg.get("model")) and (pid != "custom" or bool(cfg.get("base_url")))


def _info(pid: str, provider: Any, auto: bool, reason: str = "") -> Dict[str, Any]:
    label = PRESETS.get(pid, {}).get("label", pid)
    return {"id": pid, "label": label, "model": getattr(provider, "model", "") or "", "demo": pid == "demo", "auto": auto, "reason": reason}


def resolve(settings: Dict[str, Any], role: str, models_dir: Optional[Path]) -> Tuple[Any, Dict[str, Any]]:
    """(provedor pronto, info) do papel `role`. `info`: {id, label, model, demo, auto, reason} — `reason` explica o Demo."""
    requested = str((settings.get("active") or {}).get(role) or "auto").lower()
    if requested not in AUTO_VALUES:
        provider = build_provider(settings, requested, models_dir)
        return provider, _info(requested, provider, False)
    gen = str((settings.get("active") or {}).get("generation") or "demo")
    if role != "generation" and gen not in AUTO_VALUES and usable(settings, gen, models_dir):
        provider = build_provider(settings, gen, models_dir)
        return provider, _info(gen, provider, True)
    model = local_text_model(settings, models_dir)
    if model and _llama_installed():
        s = copy.deepcopy(settings)
        s.setdefault("providers", {}).setdefault("local_hf", {})["model"] = model
        provider = build_provider(s, "local_hf", models_dir)
        return provider, _info("local_hf", provider, True)
    if model:
        reason = f"O modelo local {model} está instalado, mas falta a biblioteca llama-cpp-python: rode  asta libs --extras local  e reinicie o ASTA."
    else:
        reason = "Nenhum provedor de IA está configurado e não há modelo local instalado."
    provider = build_provider(settings, "demo", models_dir)
    return provider, _info("demo", provider, True, reason)
