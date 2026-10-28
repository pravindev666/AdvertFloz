#!/usr/bin/env python3
"""Merge and validate AdvertFloz external-AI batches using only Python stdlib.

Expected input filenames per batch:
  365_day_prompt_library_PART_001_030.md
  365_outcomes_driven_campaigns_PART_001_030.md
  campaign_plan_PART_001_030.csv
  image_prompts_PART_001_030.csv

Run only against the marketing outputs you choose to validate. This script does not
open, execute, upload or inspect the product source repository and makes no network calls.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import timezone

RANGES = [(n, min(n + 29, 365)) for n in range(1, 361, 30)] + [(361, 365)]
RANGE_CODE = lambda a, b: f"{a:03d}_{b:03d}"
CREATIVE = "365_day_prompt_library"
OUTCOMES = "365_outcomes_driven_campaigns"
PLAN = "campaign_plan"
PROMPTS = "image_prompts"
PLAN_HEADER = ["post_id","scheduled_at","timezone","platforms","image_id","caption","enabled","campaign_tag","facebook_caption","instagram_caption","alt_text","destination_url","grace_minutes","ai_disclosure_status","notes"]
PROMPT_HEADER = ["post_id","image_id","headline","core_visual_concept","visual_grammar","prompt","negative_prompt","aspect_ratio","language","alt_text","product_claims_used"]
PLACEHOLDERS = re.compile(r"\b(?:TODO|TBD|INSERT[_ ]HERE|PLACEHOLDER|SAME AS ABOVE|SEE ABOVE)\b|\[insert[^\]]*\]|\.{3,}", re.I)
HEADING_RE = re.compile(r"(?m)^#{2,4}\s+Day\s+(\d{3})\b")


def read_csv(path: Path, errors: List[str], expected_header: List[str], kind: str) -> List[Dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            if header != expected_header:
                errors.append(f"{path.name}: header mismatch for {kind}. Expected {expected_header}; got {header}")
            rows = list(reader)
            for n, row in enumerate(rows, start=2):
                if None in row:
                    errors.append(f"{path.name}:{n}: more fields than header")
                if any(v is None for v in row.values()):
                    errors.append(f"{path.name}:{n}: fewer fields than header")
            return rows
    except (OSError, UnicodeError, csv.Error) as e:
        errors.append(f"Cannot read {path}: {e}")
        return []


def check_markdown(path: Path, expected_start: int, expected_end: int, is_creative: bool, errors: List[str], warnings: List[str]) -> str:
    try:
        content = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as e:
        errors.append(f"Cannot read {path}: {e}")
        return ""
    matches = list(HEADING_RE.finditer(content))
    ids = [int(m.group(1)) for m in matches]
    expected = list(range(expected_start, expected_end + 1))
    if ids != expected:
        errors.append(f"{path.name}: Day headings must be exactly {expected_start:03d}–{expected_end:03d} in order; found {ids}")
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i+1].start() if i + 1 < len(matches) else len(content)
        block = content[start:end]
        day = int(m.group(1))
        if f"P{day:03d}" not in block:
            errors.append(f"{path.name}: Day {day:03d} must visibly include matching post_id P{day:03d}")
        if PLACEHOLDERS.search(block):
            errors.append(f"{path.name}: Day {day:03d} contains placeholder/omitted-content marker")
        if is_creative:
            if not re.search(r"image.{0,20}prompt|creative prompt", block, re.I | re.S):
                errors.append(f"{path.name}: Day {day:03d} has no identifiable image/creative prompt heading")
            fences = re.findall(r"```[^\n]*\n(.*?)```", block, flags=re.S)
            if not fences or max((len(x.strip()) for x in fences), default=0) < 120:
                warnings.append(f"{path.name}: Day {day:03d} may not contain a complete standalone copy-ready prompt block")
            for field in ("Instagram caption", "Facebook caption"):
                if not re.search(re.escape(field), block, re.I):
                    warnings.append(f"{path.name}: Day {day:03d} has no clearly labelled {field}")
    return content


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (value or "").lower()).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path, help="Directory containing all 13 batches")
    parser.add_argument("--output-dir", required=True, type=Path, help="Destination for consolidated files and report")
    args = parser.parse_args()
    in_dir, out_dir = args.input_dir, args.output_dir
    errors: List[str] = []
    warnings: List[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    if not in_dir.is_dir():
        print(f"ERROR: input directory does not exist: {in_dir}", file=sys.stderr)
        return 2

    collected: Dict[str, List[Tuple[int, int, Path]]] = defaultdict(list)
    for start, end in RANGES:
        code = RANGE_CODE(start, end)
        for kind in (CREATIVE, OUTCOMES, PLAN, PROMPTS):
            extension = ".csv" if kind in (PLAN, PROMPTS) else ".md"
            path = in_dir / f"{kind}_PART_{code}{extension}"
            if not path.is_file():
                errors.append(f"Missing required batch file: {path.name}")
            else:
                collected[kind].append((start, end, path))

    merged_markdown: Dict[str, str] = {}
    for kind, creative in ((CREATIVE, True), (OUTCOMES, False)):
        sections = []
        for start, end, path in collected.get(kind, []):
            content = check_markdown(path, start, end, creative, errors, warnings)
            sections.append(f"\n<!-- source batch {start:03d}-{end:03d}: {path.name} -->\n\n{content.strip()}\n")
        merged_markdown[kind] = "\n".join(sections)

    merged_rows: Dict[str, List[Dict[str, str]]] = {}
    for kind, header in ((PLAN, PLAN_HEADER), (PROMPTS, PROMPT_HEADER)):
        all_rows: List[Dict[str, str]] = []
        for start, end, path in collected.get(kind, []):
            rows = read_csv(path, errors, header, kind)
            expected_count = end - start + 1
            if len(rows) != expected_count:
                errors.append(f"{path.name}: expected {expected_count} data rows, found {len(rows)}")
            all_rows.extend(rows)
        merged_rows[kind] = all_rows

    expected_posts = [f"P{i:03d}" for i in range(1, 366)]
    expected_images = list(range(1, 366))
    plan_rows = merged_rows.get(PLAN, [])
    prompt_rows = merged_rows.get(PROMPTS, [])

    post_ids = [r.get("post_id", "").strip() for r in plan_rows]
    if len(set(post_ids)) != len(post_ids):
        duplicates = sorted({x for x in post_ids if post_ids.count(x) > 1})
        errors.append(f"campaign plan has duplicate post_id values: {duplicates[:30]}")
    if sorted(post_ids) != expected_posts:
        errors.append("campaign plan post_id set must be exactly P001–P365 with no omissions/extras")
    for line, row in enumerate(plan_rows, start=2):
        post_id = row.get("post_id", "").strip()
        if row.get("enabled", "") != "false":
            errors.append(f"campaign_plan.csv row {line} ({post_id}): enabled must be exact lowercase false in AI-generated output")
        if row.get("platforms", "") not in {"facebook", "instagram", "facebook;instagram"}:
            errors.append(f"campaign_plan.csv row {line} ({post_id}): invalid platforms enum")
        try:
            iid = int(row.get("image_id", ""))
            if iid < 1 or iid > 365:
                raise ValueError
            if re.fullmatch(r"P\d{3}", post_id) and iid != int(post_id[1:]):
                errors.append(f"campaign_plan.csv row {line} ({post_id}): image_id should match post ordinal under the v1.7 default map")
        except ValueError:
            errors.append(f"campaign_plan.csv row {line} ({post_id}): image_id must be integer 1–365")
        try:
            dt = datetime.strptime(row.get("scheduled_at", ""), "%Y-%m-%dT%H:%M:%S")
            if dt.strftime("%Y-%m-%dT%H:%M:%S") != row.get("scheduled_at", ""):
                raise ValueError
        except ValueError:
            errors.append(f"campaign_plan.csv row {line} ({post_id}): scheduled_at must be YYYY-MM-DDTHH:MM:SS")
            dt = None
        tz_name = row.get("timezone", "").strip()
        try:
            tz = ZoneInfo(tz_name)
            if dt is not None:
                a0 = dt.replace(tzinfo=tz, fold=0)
                a1 = dt.replace(tzinfo=tz, fold=1)
                back0 = a0.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
                back1 = a1.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
                valid0, valid1 = back0 == dt, back1 == dt
                if not valid0 and not valid1:
                    errors.append(f"campaign_plan.csv row {line} ({post_id}): nonexistent local time during DST transition")
                elif valid0 and valid1 and a0.utcoffset() != a1.utcoffset():
                    errors.append(f"campaign_plan.csv row {line} ({post_id}): ambiguous local time during DST fall-back; choose an explicit alternative time")
        except ZoneInfoNotFoundError:
            errors.append(f"campaign_plan.csv row {line} ({post_id}): unknown IANA timezone {tz_name!r}")
        if row.get("ai_disclosure_status", "") not in {"not_reviewed", "not_required", "required_pending", "completed"}:
            errors.append(f"campaign_plan.csv row {line} ({post_id}): invalid ai_disclosure_status")
        if row.get("ai_disclosure_status", "") == "required_pending" and row.get("enabled", "") == "true":
            errors.append(f"campaign_plan.csv row {line} ({post_id}): required AI disclosure is pending")
        if row.get("destination_url", "") and not row["destination_url"].startswith("https://"):
            errors.append(f"campaign_plan.csv row {line} ({post_id}): destination_url must use HTTPS")
        effective_ig_caption = row.get("instagram_caption", "") or row.get("caption", "")
        if "instagram" in row.get("platforms", "").split(";"):
            if len(effective_ig_caption) > 2200:
                errors.append(f"campaign_plan.csv row {line} ({post_id}): Instagram caption exceeds conservative 2,200-character validation setting")
            hashtags = re.findall(r"(?<![\w])#[\w]+", effective_ig_caption, flags=re.UNICODE)
            if len(hashtags) > 5:
                errors.append(f"campaign_plan.csv row {line} ({post_id}): more than five Instagram hashtags; five is the conservative v1.7 policy setting")

    prompt_ids = [r.get("post_id", "").strip() for r in prompt_rows]
    if len(set(prompt_ids)) != len(prompt_ids):
        duplicates = sorted({x for x in prompt_ids if prompt_ids.count(x) > 1})
        errors.append(f"image_prompts.csv has duplicate post_id values: {duplicates[:30]}")
    if sorted(prompt_ids) != expected_posts:
        errors.append("image_prompts.csv post_id set must be exactly P001–P365")
    for line, row in enumerate(prompt_rows, start=2):
        try:
            iid = int(row.get("image_id", ""))
        except ValueError:
            iid = -1
        expected = int(row.get("post_id", "P000")[1:]) if re.fullmatch(r"P\d{3}", row.get("post_id", "")) else -2
        if iid != expected:
            errors.append(f"image_prompts.csv row {line}: image_id should match post ordinal for the default Pnnn convention")
        for field in ("headline", "core_visual_concept", "visual_grammar", "prompt", "aspect_ratio", "language"):
            if not row.get(field, "").strip():
                errors.append(f"image_prompts.csv row {line}: required content field {field} is blank")
        if PLACEHOLDERS.search(row.get("prompt", "")):
            errors.append(f"image_prompts.csv row {line}: prompt has placeholder/omitted-content marker")

    # Compare concept/title and caption openings for exact / likely near duplicates.
    candidates = []
    concept_items = []
    for row in prompt_rows:
        pid = row.get("post_id", "")
        concept = normalize((row.get("headline", "") + " " + row.get("core_visual_concept", "")).strip())
        if concept:
            concept_items.append((pid, concept))
    for i in range(len(concept_items)):
        pid_a, a = concept_items[i]
        for pid_b, b in concept_items[i+1:]:
            if len(a) >= 16 and len(b) >= 16:
                ratio = SequenceMatcher(None, a, b).ratio()
                if ratio >= 0.91:
                    candidates.append((pid_a, pid_b, round(ratio, 3), "headline+concept"))
    if candidates:
        warnings.append(f"Found {len(candidates)} possible near-duplicate headline/concept pairs; inspect duplicate_candidates.csv")
        with (out_dir / "duplicate_candidates.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f); w.writerow(["post_id_a","post_id_b","similarity","field"]); w.writerows(candidates)

    # Write merged Markdown files with a campaign title and clear batch provenance.
    (out_dir / "365_day_prompt_library.md").write_text("# 365-Day Prompt Library\n\nConsolidated from v1.7 external-AI batch files.\n" + merged_markdown.get(CREATIVE, ""), encoding="utf-8")
    (out_dir / "365_outcomes_driven_campaigns.md").write_text("# 365 Outcomes-Driven Campaigns\n\nConsolidated from v1.7 external-AI batch files.\n" + merged_markdown.get(OUTCOMES, ""), encoding="utf-8")
    for kind, filename, header in ((PLAN,"campaign_plan.csv",PLAN_HEADER),(PROMPTS,"image_prompts.csv",PROMPT_HEADER)):
        with (out_dir / filename).open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
            w.writeheader(); w.writerows(merged_rows.get(kind, []))

    manifest = {
        "schema_version": "1.7",
        "campaign_id": "replace-with-stable-campaign-id",
        "product_name": "REVIEW_REQUIRED",
        "start_date": "REVIEW_REQUIRED",
        "timezone_default": "REVIEW_REQUIRED",
        "planned_days": 365,
        "batch_ranges_completed": [f"{a:03d}-{b:03d}" for a,b in RANGES if all((in_dir / f"{k}_PART_{RANGE_CODE(a,b)}{'.csv' if k in (PLAN, PROMPTS) else '.md'}").is_file() for k in (CREATIVE,OUTCOMES,PLAN,PROMPTS))],
        "creative_library_file": "365_day_prompt_library.md",
        "outcomes_workbook_file": "365_outcomes_driven_campaigns.md",
        "campaign_csv_file": "campaign_plan.csv",
        "image_prompts_file": "image_prompts.csv",
        "expected_post_count": 365,
        "expected_post_ids": expected_posts,
        "expected_image_ids": expected_images,
        "enabled_default": False,
        "validation_status": "PASS" if not errors else "FAIL",
        "notes": "Replace review-required metadata before import. Validator does not inspect final image ZIPs or live Meta constraints."
    }
    (out_dir / "campaign_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = ["# AdvertFloz Campaign Batch Validation", "", f"- Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}", f"- Input: `{in_dir}`", f"- Output: `{out_dir}`", f"- Plan rows: {len(plan_rows)}", f"- Image prompt rows: {len(prompt_rows)}", f"- Creative library day headings: {sum(len(HEADING_RE.findall((in_dir / f'{CREATIVE}_PART_{RANGE_CODE(a,b)}.md').read_text(encoding='utf-8-sig'))) for a,b in RANGES if (in_dir / f'{CREATIVE}_PART_{RANGE_CODE(a,b)}.md').is_file())}", f"- Outcomes workbook day headings: {sum(len(HEADING_RE.findall((in_dir / f'{OUTCOMES}_PART_{RANGE_CODE(a,b)}.md').read_text(encoding='utf-8-sig'))) for a,b in RANGES if (in_dir / f'{OUTCOMES}_PART_{RANGE_CODE(a,b)}.md').is_file())}", "", f"## Blocking errors ({len(errors)})", ""]
    report += [f"- {e}" for e in errors] or ["- None"]
    report += ["", f"## Warnings ({len(warnings)})", ""]
    report += [f"- {w}" for w in warnings] or ["- None"]
    report += ["", "## Manual checks still required", "", "- Inspect all potential near-duplicate candidates.", "- Review destination URLs and product-feature claims against current live product.", "- Confirm timezone/DST ambiguity using the campaign's real IANA timezone rules.", "- Confirm every referenced image exists, is approved, is in a ZIP, has a matching checksum, and is remotely retrievable.", "- Confirm current Meta account eligibility, API constraints, token health, quota and AI disclosure requirements.", "- Replace `REVIEW_REQUIRED` manifest fields before import.", ""]
    (out_dir / "campaign_validation.md").write_text("\n".join(report), encoding="utf-8")

    print(f"Validation {'FAILED' if errors else 'PASSED with warnings' if warnings else 'PASSED'}: {len(errors)} blocking errors, {len(warnings)} warnings")
    print(f"Report: {out_dir / 'campaign_validation.md'}")
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
