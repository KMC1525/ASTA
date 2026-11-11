"""Esquemas, catálogos e validação do modo Data."""

from __future__ import annotations

from typing import Any, Dict, List

KINDS = ("database", "dataset")
TABS = ("main", "databases", "datasets", "synthetic", "scraping", "upgrade", "export")
EXPORT_FORMATS = ("json", "jsonl", "csv", "tsv", "sqlite")
IMPORT_FORMATS = ("json", "jsonl", "csv", "tsv")
SYNTH_MODES = ("single", "multi")
FIELD_TYPES = ("text", "number", "integer", "boolean", "json", "image", "audio", "video", "file", "url", "category")


def catalog() -> Dict[str, Any]:
    return {
        "kinds": list(KINDS),
        "tabs": [
            {"id": "main", "label": "Main"},
            {"id": "databases", "label": "Databases"},
            {"id": "datasets", "label": "Datasets"},
            {"id": "synthetic", "label": "Synthetic data"},
            {"id": "scraping", "label": "Web scraping"},
            {"id": "upgrade", "label": "Upgrade"},
            {"id": "export", "label": "Export"},
        ],
        "export_formats": list(EXPORT_FORMATS),
        "import_formats": list(IMPORT_FORMATS),
        "synth_modes": list(SYNTH_MODES),
        "field_types": list(FIELD_TYPES),
        "web_scraping_notice": {
            "open_source_only": True,
            "non_commercial": True,
            "text": "Somente para uso open source. Não usar para uso comercial. Respeite os termos, robots.txt e direitos dos sites/fontes.",
        },
    }


def clean_schema(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    fields = src.get("fields") if isinstance(src.get("fields"), list) else []
    out_fields: List[Dict[str, Any]] = []
    seen = set()
    for f in fields[:80]:
        if not isinstance(f, dict):
            continue
        name = str(f.get("name") or "").strip().replace(" ", "_")[:60]
        if not name or name in seen:
            continue
        seen.add(name)
        ftype = str(f.get("type") or "text").strip().lower()
        if ftype not in FIELD_TYPES:
            ftype = "text"
        out_fields.append({"name": name, "type": ftype, "description": str(f.get("description") or "")[:300], "required": bool(f.get("required"))})
    if not out_fields:
        out_fields = [{"name": "id", "type": "text", "description": "Identificador", "required": False}, {"name": "content", "type": "text", "description": "Conteúdo principal", "required": False}]
    return {"fields": out_fields}
