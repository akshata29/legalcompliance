"""
Azure OpenAI service wrapper — provides typed methods for each
processing phase used by both pipelines.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from openai import AzureOpenAI

from config import get_settings

logger = logging.getLogger(__name__)


class OpenAIService:
    def __init__(self) -> None:
        settings = get_settings()
        self._settings = settings
        self._client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        # Prompt capture: pipelines set this to a list to collect samples
        self.capture_log: list[dict] | None = None
        self._capture_count = 0

    # ─── Shared helper ───────────────────────────────────────────────────────

    def _chat(
        self,
        system: str,
        user: str,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> tuple[str, int]:
        """Returns (content, total_tokens_used)."""
        t0 = time.perf_counter()
        response = self._client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            temperature=temperature,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        content = response.choices[0].message.content or "{}"
        tokens = response.usage.total_tokens if response.usage else 0
        prompt_tokens = response.usage.prompt_tokens if response.usage else 0
        completion_tokens = response.usage.completion_tokens if response.usage else 0

        # Capture sample if log is active
        if self.capture_log is not None:
            self._capture_count += 1
            self.capture_log.append({
                "call_index": self._capture_count,
                "system_prompt": system,
                "user_prompt": user,
                "response_text": content,
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "latency_ms": latency_ms,
            })

        return content, tokens

    # ─── Phase A: Categorization (single provision) ──────────────────────────

    def categorize_single(
        self, provision_text: str, rules: list[dict]
    ) -> tuple[dict, int]:
        """
        Legacy path — one API call per provision.
        Returns (result_dict, tokens_used).
        """
        rules_summary = "\n".join(
            f"- {r['id']}: {r['name']} — {r['description']}" for r in rules
        )
        system = (
            "You are a legal compliance analyst. Given a provision from an EU Securities "
            "regulation document, classify it against the provided rule categories. "
            "Return ONLY a JSON object with keys: relevant (bool), categories (array of rule IDs), "
            "confidence (float 0-1)."
        )
        user = f"RULE CATEGORIES:\n{rules_summary}\n\nPROVISION:\n{provision_text}"
        content, tokens = self._chat(
            system, user, self._settings.categorization_model, max_tokens=200
        )
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {"relevant": False, "categories": [], "confidence": 0.0}
        return result, tokens

    # ─── Phase A: Categorization (batch of provisions) ───────────────────────

    def categorize_batch(
        self, provisions: list[dict], rules: list[dict]
    ) -> tuple[list[dict], int]:
        """
        Optimized path — pack up to 10 provisions into ONE API call.
        Returns (list_of_results, tokens_used).
        """
        rules_summary = "\n".join(
            f"- {r['id']}: {r['name']} — {r['description']}" for r in rules
        )
        items = "\n\n".join(
            f"[{i}] ID={p['provision_id']}\n{p['text'][:800]}"
            for i, p in enumerate(provisions)
        )
        system = (
            "You are a legal compliance analyst. Classify each numbered provision against "
            "the EU Securities rule categories below. "
            'Return ONLY a JSON object: {"results": [{"provision_id": "...", "relevant": bool, '
            '"categories": [...], "confidence": float}, ...]}. '
            "One entry per provision, in the same order."
        )
        user = f"RULE CATEGORIES:\n{rules_summary}\n\nPROVISIONS:\n{items}"
        content, tokens = self._chat(
            system, user, self._settings.categorization_model,
            max_tokens=self._settings.optimized_max_tokens_categorize
        )
        try:
            parsed = json.loads(content)
            results = parsed.get("results", [])
        except json.JSONDecodeError:
            results = []
        return results, tokens

    # ─── Phase B: Clause Extraction ──────────────────────────────────────────

    def extract_clauses(
        self, provision_id: str, provision_text: str, categories: list[str]
    ) -> tuple[list[dict], int]:
        """Extract discrete compliance clauses from a categorised provision."""
        system = (
            "You are a legal clause extractor. Given a provision and its compliance categories, "
            "identify the distinct legal obligations, prohibitions, or rights. "
            "Return ONLY JSON: {\"clauses\": [{\"clause_text\": \"...\", \"rule_category\": \"...\", "
            "\"obligation_type\": \"shall|must|may|shall_not\"}]}"
        )
        user = (
            f"CATEGORIES: {', '.join(categories)}\n\nPROVISION (ID={provision_id}):\n{provision_text}"
        )
        content, tokens = self._chat(
            system, user, self._settings.extraction_model,
            max_tokens=self._settings.optimized_max_tokens_extract
        )
        try:
            parsed = json.loads(content)
            clauses = parsed.get("clauses", [])
        except json.JSONDecodeError:
            clauses = []
        return clauses, tokens

    # ─── Phase B (Legacy): Clause Extraction per provision+rule pair ─────────

    def extract_clauses_for_rule(
        self,
        provision_id: str,
        provision_text: str,
        rule_id: str,
        rule_name: str,
        rule_description: str,
    ) -> tuple[list[dict], int]:
        """
        Legacy path — one API call per (provision, rule_category) pair.
        Mirrors reference Phase 2b (`LegalClauseExtractor`): 1 call per
        provision+rule pair, returns clause boundaries + text specific
        to that rule.

        Design doc ref: page 8, integration point #2.
        """
        system = (
            "You are a legal clause extractor. Given a provision and one specific rule category, "
            "determine whether the provision contains a clause relevant to this rule. "
            "If relevant, extract the specific clause text that addresses the rule. "
            "A provision addresses at most one aspect of a given rule. "
            "Return an empty clauses array if the provision is not relevant to this rule. "
            'Return ONLY JSON: {"clauses": [{"clause_text": "...", '
            '"obligation_type": "shall|must|may|shall_not"}]}'
        )
        user = (
            f"RULE: {rule_id} — {rule_name}\n"
            f"DESCRIPTION: {rule_description}\n\n"
            f"PROVISION (ID={provision_id}):\n{provision_text}"
        )
        content, tokens = self._chat(
            system, user, self._settings.extraction_model,
            max_tokens=self._settings.optimized_max_tokens_extract,
        )
        try:
            clauses = json.loads(content).get("clauses", [])
        except json.JSONDecodeError:
            clauses = []
        return clauses, tokens

    # ─── Phase C: Clause Analysis (Optimized — full) ─────────────────────────

    def analyze_clause(
        self, clause_id: str, clause_text: str, rule_category: str
    ) -> tuple[dict, int]:
        """Produce a compliance finding for a single extracted clause."""
        system = (
            "You are a senior EU Securities compliance officer. Analyse this clause against "
            "the specified rule category. "
            "Risk calibration — critical: potential regulatory sanction, fraud, or criminal liability; "
            "high: material non-compliance likely to attract regulatory scrutiny or significant penalty; "
            "medium: compliance gap requiring remediation; low: minor technical deviation. "
            "Err on the side of a higher risk level when the obligation is unclear or ambiguous. "
            "Return ONLY JSON: "
            "{\"finding\": \"compliant|non_compliant|needs_review|not_applicable\", "
            "\"justification\": \"...\", \"risk_level\": \"low|medium|high|critical\", "
            "\"recommendation\": \"...\"}"
        )
        user = f"RULE CATEGORY: {rule_category}\n\nCLAUSE (ID={clause_id}):\n{clause_text}"
        content, tokens = self._chat(
            system, user, self._settings.analysis_model,
            max_tokens=self._settings.optimized_max_tokens_analyze,
            temperature=0.0,
        )
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {
                "finding": "needs_review",
                "justification": "Parse error during analysis.",
                "risk_level": "medium",
                "recommendation": None,
            }
        return result, tokens

    # ─── Phase C: Step Confirmation (AiDecisionStep._prompt_decision_step_finding) ─

    def prompt_decision_step_finding(
        self,
        rule_id: str,
        rule_name: str,
        clause_findings: list[dict],
    ) -> tuple[dict, int]:
        """
        AiDecisionStep._prompt_decision_step_finding() pattern.
        Single confirmation call per AiDecisionStep (rule): receives all
        clause-level findings and returns the step-level determination.

        Path A in the reference architecture (when decision_step_confirmation_prompt
        is set on the AiDecisionStep). Not batched — 1 call per rule.
        """
        if not clause_findings:
            return {"finding": "review_required", "justification": "No clause findings.", "possible_issues": []}, 0

        findings_text = "\n".join(
            f"- Clause {i + 1}: finding={f.get('finding', 'unknown')}, "
            f"risk={f.get('risk_level', 'medium')}: {f.get('justification', '')[:200]}"
            for i, f in enumerate(clause_findings)
        )
        system = (
            "You are a senior EU Securities compliance officer. "
            "Review all clause-level findings for a compliance rule and determine the overall "
            "step finding (the AiDecisionStep determination). "
            'Return ONLY JSON: {"finding": "compliant|non_compliant|review_required", '
            '"justification": "...", "possible_issues": ["..."]}'
        )
        user = f"RULE: {rule_id} — {rule_name}\n\nCLAUSE FINDINGS:\n{findings_text}"
        content, tokens = self._chat(
            system, user, self._settings.analysis_model,
            max_tokens=300,
            temperature=0.0,
        )
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {"finding": "review_required", "justification": "Parse error.", "possible_issues": []}
        return result, tokens

