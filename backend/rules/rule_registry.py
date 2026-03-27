"""
Rule registry — loads versioned YAML rule files and resolves active versions.
Rule YAML files live in data/rules/. No code changes needed to add/update rules.
"""
from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

from rules.rule_schema import RuleDefinition, RuleVersion

logger = logging.getLogger(__name__)

_RULES_DIR = Path(__file__).parent.parent.parent / "data" / "rules"


class RuleRegistry:
    """
    Loads all YAML rule files from data/rules/ and provides:
    - get_all(): all rule definitions
    - get_active(rule_id, on_date): version active on given date
    - reload(): hot-reload rule files without restart
    """

    def __init__(self) -> None:
        self._versions: dict[str, RuleVersion] = {}
        self._load_all()

    def _load_all(self) -> None:
        _RULES_DIR.mkdir(parents=True, exist_ok=True)
        loaded = 0
        for yaml_path in _RULES_DIR.glob("*.yaml"):
            try:
                with open(yaml_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                for rule_raw in data.get("rules", []):
                    rd = self._parse_rule(rule_raw)
                    if rd.id not in self._versions:
                        self._versions[rd.id] = RuleVersion(rule_id=rd.id, versions=[])
                    self._versions[rd.id].versions.append(rd)
                    loaded += 1
            except Exception as exc:
                logger.warning("Could not load rules from %s: %s", yaml_path, exc)
        logger.info("RuleRegistry loaded %d rule definitions from %s", loaded, _RULES_DIR)

    def _parse_rule(self, raw: dict) -> RuleDefinition:
        effective_from = raw.get("effective_from")
        if isinstance(effective_from, str):
            effective_from = date.fromisoformat(effective_from)
        elif not isinstance(effective_from, date):
            effective_from = date(2019, 1, 1)

        effective_until = raw.get("effective_until")
        if isinstance(effective_until, str):
            effective_until = date.fromisoformat(effective_until)

        return RuleDefinition(
            id=raw["id"],
            version=str(raw.get("version", "1.0")),
            name=raw.get("name", raw["id"]),
            regulation=raw.get("regulation", ""),
            use_case=raw.get("use_case", "eu_sec"),
            condition=raw.get("condition", ""),
            obligation=raw.get("obligation", ""),
            evidence_fields=raw.get("evidence_fields", []),
            confidence_threshold=float(raw.get("confidence_threshold", 0.85)),
            human_review_trigger=raw.get("human_review_trigger", ""),
            effective_from=effective_from,
            effective_until=effective_until,
            supersedes=raw.get("supersedes"),
            keywords=raw.get("keywords", []),
            description=raw.get("description", raw.get("name", "")),
        )

    def get_all(self) -> list[RuleDefinition]:
        """Return the latest version of all rules."""
        today = date.today()
        result = []
        for rv in self._versions.values():
            active = rv.active_on(today)
            if active:
                result.append(active)
        return sorted(result, key=lambda r: (r.use_case, r.id))

    def get_active(self, rule_id: str, on_date: Optional[date] = None) -> Optional[RuleDefinition]:
        """Return the version of rule_id active on on_date (default: today)."""
        rv = self._versions.get(rule_id)
        if rv is None:
            return None
        return rv.active_on(on_date or date.today())

    def get_by_use_case(self, use_case: str) -> list[RuleDefinition]:
        return [r for r in self.get_all() if r.use_case == use_case]

    def reload(self) -> int:
        """Hot-reload rule files without restarting the server."""
        self._versions.clear()
        self._load_all()
        return len(self._versions)

    def to_dict_list(self) -> list[dict]:
        return [r.model_dump(mode="json") for r in self.get_all()]

    # ── Designer helpers ──────────────────────────────────────────────────────

    def _find_source_file(self, rule_id: str) -> Optional[Path]:
        """Return the YAML path that currently contains rule_id, or None."""
        for yaml_path in _RULES_DIR.glob("*.yaml"):
            try:
                with open(yaml_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if any(r.get("id") == rule_id for r in data.get("rules", [])):
                    return yaml_path
            except Exception:
                pass
        return None

    def save_rule(self, rule: "RuleDefinition") -> None:
        """
        Upsert a rule into YAML. Uses the existing source file for known rules;
        creates a per-use-case file for new rules.
        """
        source_file = self._find_source_file(rule.id) or (
            _RULES_DIR / f"{rule.use_case}_v1.yaml"
        )
        existing: list[dict] = []
        if source_file.exists():
            with open(source_file, encoding="utf-8") as f:
                existing = (yaml.safe_load(f) or {}).get("rules", [])
        existing = [r for r in existing if r.get("id") != rule.id]
        rule_dict = rule.model_dump()
        for key in ("effective_from", "effective_until"):
            val = rule_dict.get(key)
            if hasattr(val, "isoformat"):
                rule_dict[key] = val.isoformat()
            elif val is None:
                rule_dict.pop(key, None)
        existing.append(rule_dict)
        source_file.parent.mkdir(parents=True, exist_ok=True)
        with open(source_file, "w", encoding="utf-8") as f:
            yaml.dump({"rules": existing}, f, default_flow_style=False, allow_unicode=True)
        self.reload()
        logger.info("Rule '%s' saved to %s", rule.id, source_file.name)

    def delete_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID from its source YAML file. Returns True if found."""
        source_file = self._find_source_file(rule_id)
        if not source_file:
            return False
        with open(source_file, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        rules = data.get("rules", [])
        updated = [r for r in rules if r.get("id") != rule_id]
        if len(updated) == len(rules):
            return False
        with open(source_file, "w", encoding="utf-8") as f:
            yaml.dump({"rules": updated}, f, default_flow_style=False, allow_unicode=True)
        self.reload()
        logger.info("Rule '%s' deleted from %s", rule_id, source_file.name)
        return True


# ── Singleton ─────────────────────────────────────────────────────────────────
_registry: Optional[RuleRegistry] = None


def get_registry() -> RuleRegistry:
    global _registry
    if _registry is None:
        _registry = RuleRegistry()
    return _registry
