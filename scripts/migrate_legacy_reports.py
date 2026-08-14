#!/usr/bin/env python3
"""Convert legacy standalone sentiment HTML reports into fixed-template JSON."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


SENTIMENTS = ("positive", "negative", "neutral")
CARD_CLASSES = {"positive": "card-pos", "negative": "card-neg", "neutral": "card-neu"}
BADGE_CLASSES = {"positive": "badge-pos", "negative": "badge-neg", "neutral": "badge-neu"}
LANGUAGE_PLATFORM = {
    "zh": "B站",
    "en": "YouTube（英语）",
    "ja": "YouTube（日语）",
    "ko": "YouTube（韩语）",
}
PHASE_SLUG = {"上半": "upper", "下半": "lower", "完整周期": "full"}


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_int(value: Any) -> int:
    match = re.search(r"-?[\d,]+", clean_text(value))
    return int(match.group(0).replace(",", "")) if match else 0


def parse_percent(value: Any) -> float:
    match = re.search(r"-?\d+(?:\.\d+)?", clean_text(value))
    return float(match.group(0)) if match else 0.0


def slug(value: str) -> str:
    value = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip("-")
    value = re.sub(r"-+", "-", value)
    return value or "unknown"


def extract_js_values(source: str, name: str) -> list[Any]:
    pattern = re.compile(rf"\bconst\s+{re.escape(name)}\s*=")
    results: list[Any] = []
    for match in pattern.finditer(source):
        index = match.end()
        while index < len(source) and source[index].isspace():
            index += 1
        if index >= len(source) or source[index] not in "[{\"":
            continue
        if source[index] == '"':
            opening, closing = '"', '"'
        else:
            opening = source[index]
            closing = "]" if opening == "[" else "}"
        depth = 0
        in_string = False
        escaped = False
        end = index
        for end in range(index, len(source)):
            char = source[end]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    end += 1
                    break
        try:
            results.append(json.loads(source[index:end]))
        except json.JSONDecodeError:
            continue
    return results


def extract_embedded_data(source: str) -> dict[str, Any]:
    values = extract_js_values(source, "EMBEDDED_DATA")
    if values and isinstance(values[0], dict):
        return values[0]
    return {"columns": ["comment", "sentiment", "sentiment_confidence", "topics"], "rows": []}


def extract_stats(soup: BeautifulSoup, embedded: dict[str, Any]) -> dict[str, Any]:
    stats: dict[str, dict[str, Any]] = {}
    for sentiment in SENTIMENTS:
        card = soup.select_one(f".{CARD_CLASSES[sentiment]}")
        stats[sentiment] = {
            "count": parse_int(card.select_one(".count").get_text(" ", strip=True)) if card and card.select_one(".count") else 0,
            "percent": parse_percent(card.select_one(".pct").get_text(" ", strip=True)) if card and card.select_one(".pct") else 0.0,
        }

    if not sum(item["count"] for item in stats.values()):
        columns = embedded.get("columns") or []
        rows = embedded.get("rows") or []
        if "sentiment" in columns:
            sentiment_index = columns.index("sentiment")
            counts = Counter(str(row[sentiment_index]).lower() for row in rows if len(row) > sentiment_index)
            total = sum(counts.get(key, 0) for key in SENTIMENTS)
            for sentiment in SENTIMENTS:
                count = counts.get(sentiment, 0)
                stats[sentiment] = {"count": count, "percent": round(count / total * 100, 1) if total else 0.0}

    total = sum(item["count"] for item in stats.values())
    if total:
        for sentiment in SENTIMENTS:
            if stats[sentiment]["percent"] == 0 and stats[sentiment]["count"]:
                stats[sentiment]["percent"] = round(stats[sentiment]["count"] / total * 100, 1)
    return {"total_comments": total, "sentiments": stats}


def choose_topic_arrays(source: str) -> tuple[list[str], list[int], list[int], list[int]]:
    pos_values = extract_js_values(source, "topicPosData") or extract_js_values(source, "topicPos")
    neg_values = extract_js_values(source, "topicNegData") or extract_js_values(source, "topicNeg")
    neu_values = extract_js_values(source, "topicNeuData") or extract_js_values(source, "topicNeu")
    pos = pos_values[0] if pos_values else []
    neg = neg_values[0] if neg_values else []
    neu = neu_values[0] if neu_values else []
    expected = min(len(pos), len(neg), len(neu))

    label_candidates = extract_js_values(source, "topicLabels") + extract_js_values(source, "topicData") + extract_js_values(source, "labels")
    labels: list[str] = []
    for candidate in label_candidates:
        if isinstance(candidate, list) and len(candidate) == expected and expected:
            labels = [clean_text(item) for item in candidate]
            if not set(labels).issubset({"正面", "负面", "中性"}):
                break
    return labels[:expected], [int(x) for x in pos[:expected]], [int(x) for x in neg[:expected]], [int(x) for x in neu[:expected]]


def extract_topics(source: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labels, pos, neg, neu = choose_topic_arrays(source)
    rows = []
    for name, positive, negative, neutral in zip(labels, pos, neg, neu):
        total = positive + negative + neutral
        rows.append({
            "name": name,
            "total": total,
            "positive_percent": round(positive / total * 100, 1) if total else 0.0,
            "negative_percent": round(negative / total * 100, 1) if total else 0.0,
            "neutral_percent": round(neutral / total * 100, 1) if total else 0.0,
        })
    rows.sort(key=lambda item: item["total"], reverse=True)
    top = rows[:10]
    keywords = [{"name": item["name"], "count": item["total"]} for item in top]
    return keywords, top


def sentiment_for_block(block: Any) -> str | None:
    for sentiment, class_name in BADGE_CLASSES.items():
        if block.select_one(f".{class_name}"):
            return sentiment
    return None


def empty_topic(rank: int) -> dict[str, Any]:
    return {"rank": rank, "title": "", "detail": "", "count": None, "share_percent": None, "quotes": []}


def extract_insights(soup: BeautifulSoup) -> tuple[dict[str, Any], dict[str, Any]]:
    generated = {sentiment: {"summary": "", "topics": [empty_topic(i) for i in range(1, 4)]} for sentiment in SENTIMENTS}
    legacy = {"unmapped_quotes": {sentiment: [] for sentiment in SENTIMENTS}, "overall_tone": {sentiment: "" for sentiment in SENTIMENTS}}
    for block in soup.select(".insight-block"):
        sentiment = sentiment_for_block(block)
        if not sentiment:
            continue
        body = block.select_one(".insight-body") or block
        summary = block.select_one(".insight-header .summary-text") or body.select_one(".summary-para, .summary-text")
        generated[sentiment]["summary"] = clean_text(summary.get_text(" ", strip=True)) if summary else ""
        tone = body.select_one(".tone")
        legacy["overall_tone"][sentiment] = clean_text(tone.get_text(" ", strip=True)).removeprefix("情感基调：") if tone else ""
        topics = []
        for rank, area in enumerate(body.select(".focus-area")[:3], 1):
            strong = area.find("strong")
            title = clean_text(strong.get_text(" ", strip=True) if strong else area.get_text(" ", strip=True))
            title = re.sub(r"^[🔥📌•·\s]+", "", title)
            full_text = clean_text(area.get_text(" ", strip=True))
            detail = full_text[len(clean_text(strong.get_text(" ", strip=True))):].lstrip("：: ") if strong else ""
            topics.append({"rank": rank, "title": title, "detail": detail, "count": None, "share_percent": None, "quotes": []})
        while len(topics) < 3:
            topics.append(empty_topic(len(topics) + 1))
        generated[sentiment]["topics"] = topics
        legacy["unmapped_quotes"][sentiment] = [clean_text(node.get_text(" ", strip=True)).strip("「」") for node in body.select(".quotes .q")]
    return generated, legacy


def extract_conclusion(soup: BeautifulSoup) -> str:
    box = soup.select_one(".conclusion-box")
    if not box:
        return ""
    paragraph = box.find("p")
    return clean_text(paragraph.get_text(" ", strip=True) if paragraph else box.get_text(" ", strip=True)).removeprefix("📋 总结论")


def extract_generated_at(soup: BeautifulSoup) -> str:
    footer = clean_text(soup.footer.get_text(" ", strip=True) if soup.footer else "")
    match = re.search(r"(20\d{2}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::\d{2})?", footer)
    return f"{match.group(1)}T{match.group(2)}:00+08:00" if match else datetime.now().astimezone().isoformat(timespec="seconds")


def report_paths(game: dict[str, Any], phase: dict[str, Any], lang: str) -> tuple[str, str]:
    phase_name = PHASE_SLUG.get(phase.get("phase", ""), slug(phase.get("phase", "phase")))
    base = f"{game['id']}-{slug(str(phase['version']))}-{phase_name}-{lang}"
    return f"data/reports/{base}.json", f"data/report-data/{base}-annotations.json"


def build_report(root: Path, game: dict[str, Any], phase: dict[str, Any], lang: str, legacy_href: str) -> tuple[dict[str, Any], dict[str, Any]]:
    source = (root / legacy_href).read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(source, "html.parser")
    embedded = extract_embedded_data(source)
    stats = extract_stats(soup, embedded)
    keywords, topics = extract_topics(source)
    sentiments, legacy_insights = extract_insights(soup)
    characters = " / ".join(item.get("name", "") for item in phase.get("characters", []) if item.get("name")) or "全角色"
    report_path, annotations_path = report_paths(game, phase, lang)
    report = {
        "schema_version": 1,
        "meta": {
            "game": game["name"], "version": str(phase["version"]), "phase": phase["phase"],
            "character": characters, "date_start": phase["start"], "date_end": phase["end"],
            "platform": LANGUAGE_PLATFORM.get(lang, lang), "generated_at": extract_generated_at(soup),
        },
        "analysis": {**stats, "keywords": keywords, "topics": topics},
        "generated": {"overall_conclusion": extract_conclusion(soup), "sentiments": sentiments},
        "editorial_override": {
            "overall_conclusion": None,
            "sentiments": {sentiment: {"summary": None, "topics": [None, None, None]} for sentiment in SENTIMENTS},
            "updated_at": None,
        },
        "annotated_data": {
            "columns": embedded.get("columns") or ["comment", "sentiment", "sentiment_confidence", "topics"],
            "rows": [], "download_url": annotations_path,
        },
        "migration": {
            "source_html": legacy_href, "method": "legacy-html-extraction-v1",
            "notes": "旧报告未明确关联代表评论与各TOP3，未自动错配。",
            **legacy_insights,
        },
    }
    annotations = {
        "columns": embedded.get("columns") or ["comment", "sentiment", "sentiment_confidence", "topics"],
        "rows": embedded.get("rows") or [],
    }
    return report, annotations


def validate_report(report: dict[str, Any]) -> list[str]:
    errors = []
    for key in ("schema_version", "meta", "analysis", "generated", "editorial_override", "annotated_data"):
        if key not in report:
            errors.append(f"missing {key}")
    sentiments = report.get("analysis", {}).get("sentiments", {})
    if set(sentiments) != set(SENTIMENTS):
        errors.append("invalid sentiment keys")
    if sum(item.get("count", 0) for item in sentiments.values()) != report.get("analysis", {}).get("total_comments"):
        errors.append("sentiment counts do not sum to total")
    if len(report.get("analysis", {}).get("keywords", [])) > 10 or len(report.get("analysis", {}).get("topics", [])) > 10:
        errors.append("keywords/topics exceed Top10")
    for sentiment in SENTIMENTS:
        if len(report.get("generated", {}).get("sentiments", {}).get(sentiment, {}).get("topics", [])) != 3:
            errors.append(f"{sentiment} does not contain exactly Top3 slots")
    return errors


def migrate(site_dir: Path, dry_run: bool) -> dict[str, int]:
    catalog_path = site_dir / "data/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    summary = Counter()
    for game in catalog["games"]:
        for phase in game["phases"]:
            for lang, entry in (phase.get("reports") or {}).items():
                legacy_href = entry.get("legacy_href") or entry.get("href")
                if entry.get("status") != "ready" or not legacy_href:
                    continue
                report, annotations = build_report(site_dir, game, phase, lang, legacy_href)
                errors = validate_report(report)
                if errors:
                    raise ValueError(f"{legacy_href}: {'; '.join(errors)}")
                report_path, annotations_path = report_paths(game, phase, lang)
                summary["reports"] += 1
                summary["comments"] += report["analysis"]["total_comments"]
                summary["embedded_rows"] += len(annotations["rows"])
                summary["missing_conclusions"] += not bool(report["generated"]["overall_conclusion"])
                summary["missing_summaries"] += sum(not bool(report["generated"]["sentiments"][key]["summary"]) for key in SENTIMENTS)
                summary["empty_top3_slots"] += sum(not topic["title"] for key in SENTIMENTS for topic in report["generated"]["sentiments"][key]["topics"])
                if not dry_run:
                    report_target, annotations_target = site_dir / report_path, site_dir / annotations_path
                    report_target.parent.mkdir(parents=True, exist_ok=True)
                    annotations_target.parent.mkdir(parents=True, exist_ok=True)
                    if report_target.is_file():
                        existing = json.loads(report_target.read_text(encoding="utf-8"))
                        if existing.get("editorial_override"):
                            report["editorial_override"] = existing["editorial_override"]
                    report_target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    annotations_target.write_text(json.dumps(annotations, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
                    entry.pop("href", None)
                    entry["data_source"] = report_path
                    entry["legacy_href"] = legacy_href
                    entry["download_name"] = entry.get("download_name") or Path(legacy_href).name
    if not dry_run:
        catalog["updated_at"] = datetime.now().date().isoformat()
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dict(summary)


def check(site_dir: Path) -> dict[str, int]:
    catalog = json.loads((site_dir / "data/catalog.json").read_text(encoding="utf-8"))
    summary = Counter()
    for game in catalog["games"]:
        for phase in game["phases"]:
            for lang, entry in (phase.get("reports") or {}).items():
                if entry.get("status") != "ready":
                    continue
                summary["ready"] += 1
                data_source, legacy_href = entry.get("data_source"), entry.get("legacy_href")
                if not data_source or not (site_dir / data_source).is_file():
                    raise FileNotFoundError(f"missing data_source for {game['name']} {phase['version']} {phase['phase']} {lang}")
                if not legacy_href or not (site_dir / legacy_href).is_file():
                    raise FileNotFoundError(f"missing legacy backup for {data_source}")
                report = json.loads((site_dir / data_source).read_text(encoding="utf-8"))
                errors = validate_report(report)
                if errors:
                    raise ValueError(f"{data_source}: {'; '.join(errors)}")
                download_url = report["annotated_data"].get("download_url")
                if download_url and not (site_dir / download_url).is_file():
                    raise FileNotFoundError(f"missing annotation data for {data_source}")
                summary["comments"] += report["analysis"]["total_comments"]
    return dict(summary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-dir", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = check(args.site_dir) if args.check else migrate(args.site_dir, args.dry_run)
    label = "CHECK" if args.check else "DRY-RUN" if args.dry_run else "MIGRATED"
    print(f"[OK] {label} {json.dumps(result, ensure_ascii=False, sort_keys=True)}")


if __name__ == "__main__":
    main()
