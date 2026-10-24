"""Free-text field reports -> validated stock counts (Bedrock, with a deterministic rules parser).

The parse is only a proposal: a coordinator confirms it before it is ingested as a report.
"""

from __future__ import annotations

import json
import logging
import re

from engine.estimator import estimate
from explain import bedrock_client
from lantern_core import ids, store
from lantern_core.config import SUPPLY_ORDER, settings, utc_now_iso
from lantern_core.schemas import FieldReportParse

log = logging.getLogger(__name__)

SITE_ALIASES = {
    "S01": ["shelter a", "shelter 1"],
    "S02": ["shelter b", "shelter 2"],
    "S03": ["riverside", "clinic"],
    "S04": ["central pharmacy", "pharmacy", "central"],
    "S05": ["food bank", "county food bank"],
}
SUPPLY_KEYWORDS = {
    "insulin": ["insulin", "vial", "vials"],
    "water": ["water", "gallon", "gallons", "gal"],
    "food": ["food", "meal", "meals", "mre", "mres"],
}
HEDGES = ["maybe", "about", "around", "approx", "approximately", "roughly", "i think", "guess", "not sure", "or so", "~"]
NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "dozen": 12, "fifteen": 15, "twenty": 20,
}  # fmt: skip
NEAR_CHARS = 30
RULES_BASE_CONFIDENCE = 0.75

SYSTEM_PROMPT = (
    "You extract ONE stock count from a short field report written by a scout or volunteer during a disaster. "
    "Use only the site ids and supply ids you are given. If you cannot tell the site, supply or quantity, use null. "
    "If the text gives a number but hedges it (maybe 1, about 20, around 5), still report that number as qty "
    "and lower your confidence instead. Report your confidence from 0 to 1; lower it when the text hedges "
    "(maybe, about, around) or is ambiguous. "
    "Do not make decisions or recommendations. Reply with JSON only: "
    '{"site_id": "S04" | null, "supply_id": "insulin" | null, "qty": number | null, "confidence": number, "notes": "<short>"}'
)


def _sites(scenario_id: str, sites: list | None) -> list[dict]:
    rows = sites if sites is not None else store.query_pk(settings.TABLE_SITES, scenario_id)
    return [s if isinstance(s, dict) else s.model_dump() for s in rows]


def _aliases(site: dict) -> list[str]:
    return sorted({*SITE_ALIASES.get(site["site_id"], []), site["name"].lower(), site["site_id"].lower()}, key=len, reverse=True)


def _find_all(text: str, phrase: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text)]


def parse_rules(text: str, sites: list[dict]) -> dict:
    t = text.lower()
    # site: longest alias wins; shorter aliases inside a longer match are ignored
    matches = []
    for s in sites:
        for alias in _aliases(s):
            matches.extend((a, b, s["site_id"]) for a, b in _find_all(t, alias))
    matches.sort(key=lambda m: (m[0], -(m[1] - m[0])))
    kept: list[tuple[int, int, str]] = []
    for m in matches:
        if not any(k[0] <= m[0] and m[1] <= k[1] for k in kept):
            kept.append(m)
    site_ids = list(dict.fromkeys(m[2] for m in kept))
    spans = [(m[0], m[1]) for m in kept]

    # numbers (digits or small number words), excluding ones inside a site name ("shelter 2")
    numbers = []
    for m in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])", t):
        numbers.append((m.start(), m.end(), float(m.group(1))))
    for word, val in NUMBER_WORDS.items():
        numbers.extend((a, b, float(val)) for a, b in _find_all(t, word))
    numbers = [n for n in numbers if not any(a <= n[0] and n[1] <= b for a, b in spans)]

    # supply: the keyword closest to a number
    best = None
    supplies_seen = []
    for supply, words in SUPPLY_KEYWORDS.items():
        for w in words:
            for a, b in _find_all(t, w):
                supplies_seen.append(supply)
                for na, nb, val in numbers:
                    gap = a - nb if nb <= a else na - b if na >= b else 0
                    if gap <= NEAR_CHARS and (best is None or gap < best[0]):
                        best = (gap, supply, val)
    supplies_seen = list(dict.fromkeys(supplies_seen))

    notes, problems = [], []
    site_id = site_ids[0] if site_ids else None
    supply_id = best[1] if best else (supplies_seen[0] if supplies_seen else None)
    qty = best[2] if best else None
    confidence = RULES_BASE_CONFIDENCE
    if not site_id:
        problems.append("No known site found in the text.")
        confidence = min(confidence, 0.2)
    if len(site_ids) > 1:
        notes.append(f"Several sites mentioned ({', '.join(site_ids)}); took the first.")
        confidence -= 0.2
    if not supply_id:
        problems.append("No known supply found in the text.")
        confidence = min(confidence, 0.2)
    if qty is None:
        problems.append("No quantity found near a supply word.")
        confidence = min(confidence, 0.2)
    hedges = [h for h in HEDGES if (h in t if not h[0].isalpha() else _find_all(t, h))]
    if hedges:
        notes.append(f"Hedged wording ({', '.join(hedges)}).")
        confidence -= 0.3
    if site_id and supply_id and qty is not None:
        notes.insert(0, f"Rules parser: {site_id}, {supply_id}, {qty:g}.")
    return {
        "site_id": site_id,
        "supply_id": supply_id,
        "qty": qty,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "notes": " ".join(notes),
        "problems": problems,
    }


def _bedrock_parse(text: str, sites: list[dict]) -> tuple[dict, str, str]:
    catalog = {
        "sites": [{"site_id": s["site_id"], "name": s["name"], "aliases": SITE_ALIASES.get(s["site_id"], [])} for s in sites],
        "supplies": [{"supply_id": k, "unit": settings.unit(k)} for k in SUPPLY_ORDER],
    }
    user = f"Known sites and supplies (JSON):\n{json.dumps(catalog)}\n\nField report:\n{text}"
    last_err: Exception | None = None
    for model_id in bedrock_client.model_ids():
        try:
            reply = bedrock_client.converse_text(model_id, SYSTEM_PROMPT, user, max_tokens=300, temperature=0.0)
            obj = bedrock_client.extract_json(reply)
            known_sites = {s["site_id"] for s in sites}
            site_id, supply_id = obj.get("site_id"), obj.get("supply_id")
            qty, conf = obj.get("qty"), obj.get("confidence", 0.5)
            problems = []
            if site_id is not None and site_id not in known_sites:
                problems.append(f"Unknown site {site_id!r}.")
                site_id = None
            if site_id is None and not problems:
                problems.append("No known site found in the text.")
            if supply_id is not None and supply_id not in SUPPLY_ORDER:
                problems.append(f"Unknown supply {supply_id!r}.")
                supply_id = None
            if supply_id is None and not any("supply" in p for p in problems):
                problems.append("No known supply found in the text.")
            if qty is not None and not isinstance(qty, int | float):
                raise ValueError(f"qty is not a number: {qty!r}")
            if qty is None:
                problems.append("No quantity found.")
            conf = float(conf)
            if not 0.0 <= conf <= 1.0:
                raise ValueError(f"confidence out of range: {conf}")
            parsed = {
                "site_id": site_id,
                "supply_id": supply_id,
                "qty": float(qty) if qty is not None else None,
                "confidence": round(conf, 2),
                "notes": str(obj.get("notes") or "")[:300],
                "problems": problems,
            }
            return parsed, model_id, reply
        except Exception as e:
            last_err = e
            log.warning("bedrock field-report parse failed with %s: %s", model_id, e)
    raise RuntimeError(f"bedrock parse failed: {last_err}")


def _next_id(scenario_id: str, sim_hour: int) -> str:
    prefix = f"raw/scenarios/{scenario_id}/field_reports/fr_{scenario_id}_h{int(sim_hour):03d}_"
    return ids.field_report_id(scenario_id, sim_hour, len(store.list_keys(prefix)) + 1)


def audit_key(scenario_id: str, field_report_id: str) -> str:
    return f"raw/scenarios/{scenario_id}/field_reports/{field_report_id}.json"


def parse_field_report(scenario_id: str, text: str, inventory: list | None = None, sites: list | None = None) -> FieldReportParse:
    sites_l = _sites(scenario_id, sites)
    inv_rows = inventory if inventory is not None else store.query_pk(settings.TABLE_INVENTORY, scenario_id)
    rows = {r["site_supply"]: r for r in estimate(inv_rows)}
    sim_hour = max((int(r["sim_hour"]) for r in rows.values()), default=0)

    source, model_id, reply = "rules", None, None
    parsed = None
    if settings.BEDROCK_ENABLED:
        try:
            parsed, model_id, reply = _bedrock_parse(text, sites_l)
            source = "bedrock"
        except Exception as e:
            log.warning("falling back to the rules parser: %s", e)
    if parsed is None:
        parsed = parse_rules(text, sites_l)

    problems = list(parsed["problems"])
    notes = [parsed["notes"]] if parsed["notes"] else []
    hold = []
    qty, site_id, supply_id = parsed["qty"], parsed["site_id"], parsed["supply_id"]
    row = rows.get(ids.site_supply(site_id, supply_id)) if site_id and supply_id else None
    if site_id and supply_id and row is None:
        problems.append(f"No inventory row for {site_id} {supply_id}.")
    if qty is not None and row is not None:
        p05, p95 = float(row["est_qty_p05"]), float(row["est_qty_p95"])
        upper = max(3 * p95, 10.0)
        if not 0 <= qty <= upper:
            problems.append(f"Quantity {qty:g} is outside the plausible range 0 to {upper:.0f}.")
        elif not p05 * 0.5 <= qty <= p95 * 1.5:
            hold.append(f"Count {qty:g} is outside the expected range {p05 * 0.5:.1f} to {p95 * 1.5:.1f}.")
    if parsed["confidence"] < settings.FIELD_REPORT_MIN_CONFIDENCE:
        hold.append(f"Low confidence ({parsed['confidence']:.2f} < {settings.FIELD_REPORT_MIN_CONFIDENCE:.2f}).")
    if hold:
        notes.append("Held for confirmation: " + " ".join(hold))

    result = FieldReportParse(
        field_report_id=_next_id(scenario_id, sim_hour),
        scenario_id=scenario_id,
        sim_hour=sim_hour,
        source_text=text,
        site_id=site_id,
        supply_id=supply_id,
        qty=qty,
        confidence=parsed["confidence"],
        notes=" ".join(notes),
        parser_source=source,
        needs_confirmation=bool(hold or problems),
        problems=problems,
    )
    store.put_json(
        audit_key(scenario_id, result.field_report_id),
        {"parse": result.to_item(), "model_id": model_id, "raw_reply": reply, "created_at": utc_now_iso()},
    )
    log.info("field report %s parser_source=%s", result.field_report_id, source)
    return result
