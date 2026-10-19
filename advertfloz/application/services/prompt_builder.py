"""Marketing Prompt Builder (FR-001, FR-002, FR-003).

Fills the bundled master-prompt template with operator inputs and returns downloadable
artifacts. It performs template substitution only: no AI calls, no repository scanning and
no network access.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources

from ...domain.scheduling import is_valid_iana

PLACEHOLDERS = (
    "PRODUCT_NAME",
    "PRODUCT_URL",
    "TARGET_MARKETS",
    "TARGET_AUDIENCES",
    "LANGUAGES",
    "BRAND_TONE",
    "CAMPAIGN_START_DATE",
    "POSTING_TIME",
    "TIMEZONE",
    "CADENCE",
    "PLATFORMS",
    "PRIMARY_OUTCOME",
    "CAMPAIGN_TAG",
    "DESTINATION_URLS",
    "FEATURES_TO_VERIFY",
    "CLAIMS_TO_AVOID",
    "ART_DIRECTION",
    "OTHER_NOTES",
    "IMAGE_TYPOGRAPHY_INSTRUCTION",
    "PLANNED_DAYS",
    "PLANNED_DAYS_PAD",
    "BATCH_SCHEDULE_INSTRUCTION",
    "OFFER_HOOK",
    "REAL_WORLD_MIX_INSTRUCTION",
)


@dataclass
class BriefInputs:
    product_name: str = ""
    product_url: str = ""
    target_markets: str = ""
    target_audiences: str = ""
    languages: str = "English"
    brand_tone: str = ""
    campaign_start_date: str = ""
    posting_time: str = "09:00"
    timezone: str = "Asia/Kolkata"
    cadence: str = "daily"
    platforms: str = "facebook;instagram"
    primary_outcome: str = ""
    campaign_tag: str = ""
    destination_urls: str = ""
    features_to_verify: str = "verify against uploaded repo"
    claims_to_avoid: str = ""
    art_direction: str = ""
    other_notes: str = ""
    image_typography_mode: str = "ai_poster"
    planned_days: int = 365
    offer_hook: str = ""

    def as_mapping(self) -> dict[str, str]:
        if self.image_typography_mode == "manual":
            typo_instruction = (
                "MANUAL OVERLAY MODE: Image generation prompts must instruct tools NOT to render text or logos, "
                "leaving clean, open negative space so the user can manually add the headline and logo in Canva or Figma."
            )
        else:
            typo_instruction = (
                "DIRECT FINISHED AI POSTER (CLIENT HAS NO TIME FOR CANVA): Every image prompt must instruct the AI "
                "to generate a finished social-feed poster creative with the exact headline and brand name cleanly and boldly "
                "typeset directly onto the image with high-contrast, modern typography. "
                "STRICT SPELLING VERIFICATION: The prompt must instruct the image generator to double-check every letter and word "
                "of the headline and brand name before rendering to ensure 100% correct spelling, zero typos, and clear readability on mobile."
            )

        days = max(1, min(365, int(self.planned_days or 365)))
        days_pad = f"{days:03d}"

        if days <= 30:
            batch_instr = (
                f"BATCH SIZES — SINGLE BATCH DELIVERY ({days} DAYS TOTAL)\n"
                f"Because this campaign duration is {days} days (<= 30 days), create all {days} days in ONE single response:\n"
                f"- Range: 001–{days_pad} (post_ids P001 to P{days_pad}, image_ids 1 to {days}, filenames 1.jpg to {days}.jpg).\n"
                f"Deliver in your response:\n"
                f"- `365_day_prompt_library_PART_001_{days_pad}.md` (and final `365_day_prompt_library.md`)\n"
                f"- `365_outcomes_driven_campaigns_PART_001_{days_pad}.md` (and final `365_outcomes_driven_campaigns.md`)\n"
                f"- `campaign_plan_PART_001_{days_pad}.csv` (and final `campaign_plan.csv` with exactly {days} rows)\n"
                f"- `image_prompts_PART_001_{days_pad}.csv` (and final `image_prompts.csv` with exactly {days} rows)\n"
                f"- `campaign_manifest.json` (planned_days: {days}, post_count: {days}, expected_post_ids: P001..P{days_pad})\n"
                f"- `continuity_ledger.md` and `batch_checklist_001_{days_pad}.md`\n"
                f"No multi-turn continuation prompts needed; deliver the full {days}-day package in this response."
            )
        else:
            ranges = []
            curr = 1
            while curr <= days:
                end = min(curr + 29, days)
                ranges.append(f"{curr:03d}–{end:03d}")
                curr = end + 1
            ranges_str = ", ".join(ranges)

            batch_instr = (
                f"BATCH SIZES — NEVER TRY TO WRITE ALL {days} ENTRIES IN ONE RESPONSE\n"
                f"Create exactly one batch per response across {len(ranges)} fixed ranges:\n"
                f"{ranges_str}.\n"
                f"First response: only batch 001–030. Create:\n"
                f"- `365_day_prompt_library_PART_001_030.md`\n"
                f"- `365_outcomes_driven_campaigns_PART_001_030.md`\n"
                f"- `campaign_plan_PART_001_030.csv`\n"
                f"- `image_prompts_PART_001_030.csv`\n"
                f"Also update `continuity_ledger.md` and create `batch_checklist_001_030.md`. Stop after this batch and tell the user the next range. Use the separate batch/consolidation prompt to continue and merge after all batches are available."
            )

        real_world_mix = (
            "REAL-WORLD CONTENT STRATEGY & DYNAMIC VISUAL MIX (MANDATORY ANTI-BOREDOM RULE):\n"
            "To prevent audience fatigue and maximize social media conversions, you MUST systematically rotate through these 5 content pillars and 5 visual art styles. Never repeat the same pillar or visual style two days in a row:\n\n"
            "1. DYNAMIC CONTENT PILLARS:\n"
            "   - Pillar 1 (Actionable Tips & Education, ~30%): Practical music theory shortcuts, notation hacks, and pro tips providing immediate value to teachers and students.\n"
            "   - Pillar 2 (Feature Spotlight & Workflow, ~25%): Real in-depth look at verified product features (e.g. audio-to-sheet-music transcription, MIDI/MusicXML export, browser playback).\n"
            "   - Pillar 3 (Pain Relief & Contrast, ~20%): Relatable frustrations (messy handwritten papers, lost arrangements) contrasted with effortless notation.\n"
            "   - Pillar 4 (Practical Scenario Walkthroughs, ~15%): Step-by-step real use cases (e.g. prep a 2-measure exercise in 2 minutes before a lesson).\n"
            "   - Pillar 5 (Engagement & Discussion, ~10%): Thought-provoking questions encouraging comments, saves, and teacher discussions.\n\n"
            "2. DYNAMIC VISUAL ART STYLES (Rotate across days):\n"
            "   - Style A (Modern SaaS / Desktop Still Life): Clean notation canvas card on an ivory desk, subtle shadows, pencil, and tasteful browser frame.\n"
            "   - Style B (Warm Studio Photography): Atmospheric overhead studio still life with piano/guitar acoustic elements, wooden desk, coffee cup, sheet music, and warm natural sunlight.\n"
            "   - Style C (Bold Swiss Typographic Poster): High-contrast graphic poster with bold clean typography, elegant music notation geometry, and strong brand color accents.\n"
            "   - Style D (Artisan Macro Detail): Close-up focus on crisp engraved staves, clefs, and notes on fine textured score paper, conveying precision.\n"
            "   - Style E (Two-Step Input/Output Diagram): Clean visual split showing audio/melody idea transforming seamlessly into engraved sheet music.\n\n"
            "3. MOBILE FIRST-FOLD HOOK RULE (125-CHARACTER RULE):\n"
            "   - Instagram and Facebook feeds truncate captions with '... more' after ~125 characters on mobile screens.\n"
            "   - The very first sentence (under 125 characters) of EVERY caption MUST contain an irresistible hook, compelling question, or strong benefit before the fold.\n"
            "   - Never waste the first 125 characters on greetings, dates, hashtags, or introductory filler."
        )

        offer_text = self.offer_hook.strip() if self.offer_hook else "None specified (focus on product value and free tier/instant access)"

        return {
            "PRODUCT_NAME": self.product_name,
            "PRODUCT_URL": self.product_url,
            "TARGET_MARKETS": self.target_markets,
            "TARGET_AUDIENCES": self.target_audiences,
            "LANGUAGES": self.languages,
            "BRAND_TONE": self.brand_tone,
            "CAMPAIGN_START_DATE": self.campaign_start_date,
            "POSTING_TIME": self.posting_time,
            "TIMEZONE": self.timezone,
            "CADENCE": self.cadence,
            "PLATFORMS": self.platforms,
            "PRIMARY_OUTCOME": self.primary_outcome,
            "CAMPAIGN_TAG": self.campaign_tag,
            "DESTINATION_URLS": self.destination_urls,
            "FEATURES_TO_VERIFY": self.features_to_verify,
            "CLAIMS_TO_AVOID": self.claims_to_avoid,
            "ART_DIRECTION": self.art_direction,
            "OTHER_NOTES": self.other_notes,
            "IMAGE_TYPOGRAPHY_INSTRUCTION": typo_instruction,
            "PLANNED_DAYS": str(days),
            "PLANNED_DAYS_PAD": days_pad,
            "BATCH_SCHEDULE_INSTRUCTION": batch_instr,
            "OFFER_HOOK": offer_text,
            "REAL_WORLD_MIX_INSTRUCTION": real_world_mix,
        }


@dataclass
class BriefValidation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


REQUIRED_FIELDS = ("product_name", "product_url", "target_markets", "campaign_start_date", "campaign_tag")


def validate_brief(brief: BriefInputs) -> BriefValidation:
    result = BriefValidation()
    for name in REQUIRED_FIELDS:
        if not getattr(brief, name).strip():
            result.errors.append(f"{name} is required")
    if brief.product_url and not brief.product_url.startswith("https://"):
        result.errors.append("product_url must start with https://")
    if not is_valid_iana(brief.timezone):
        result.errors.append(f"timezone must be a valid IANA zone, not {brief.timezone!r}")
    if brief.platforms not in {"facebook", "instagram", "facebook;instagram"}:
        result.errors.append("platforms must be facebook, instagram or facebook;instagram")
    for url in [u.strip() for u in brief.destination_urls.split(",") if u.strip()]:
        if not url.startswith("https://"):
            result.errors.append(f"destination URL must be HTTPS: {url}")
    if not brief.features_to_verify.strip():
        result.warnings.append("features_to_verify is blank; the LLM will not know what to re-verify")
    return result


def _read_template(name: str) -> str:
    return resources.files("advertfloz.templates").joinpath(name).read_text(encoding="utf-8")


def build_master_prompt(brief: BriefInputs) -> str:
    template = _read_template("master_prompt_template.txt")
    for key, value in brief.as_mapping().items():
        template = template.replace("{{" + key + "}}", value)
    return template


def build_batch_continuation_prompt() -> str:
    return _read_template("batch_continuation_prompt.txt")


def build_output_contract() -> str:
    return _read_template("output_contract.md")


def build_brief_backup(brief: BriefInputs) -> str:
    """A human-readable copy of the inputs, for the operator's own records."""
    lines = ["# AdvertFloz campaign brief (backup copy)", ""]
    for key, value in brief.as_mapping().items():
        lines.append(f"- **{key}**: {value}")
    lines += [
        "",
        "Reminder: upload your product repository directly to your chosen external AI yourself.",
        "AdvertFloz does not receive or scan that repository.",
    ]
    return "\n".join(lines)


def what_happens_next() -> list[str]:
    return [
        "1. Download the master prompt and the batch/consolidation instructions.",
        "2. Upload your product repository to your chosen external AI and paste the master prompt.",
        "3. Generate the 13 fixed batches, then run the consolidation prompt to merge and validate.",
        "4. Return here with campaign_plan.csv and your image ZIP parts to import.",
    ]
