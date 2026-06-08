from __future__ import annotations

import asyncio
import traceback

import db
from agents import (
    dossier_compiler,
    homepage_scout,
    hypothesis_builder,
    linkedin_analyst,
    linkedin_search,
    news_scout,
    outreach_angles,
    scorer,
    signal_extractor,
)
from config import settings
from integrations import pipedrive


async def run_pipeline(
    run_id: int, accounts: list[dict], value_prop: str
) -> None:
    try:
        await db.update_run_status(run_id, "running")
        batch_size = max(1, settings.batch_size)
        for start in range(0, len(accounts), batch_size):
            batch = accounts[start : start + batch_size]
            await asyncio.gather(
                *(process_account(run_id, a, value_prop) for a in batch)
            )
            await db.update_run_counts(run_id)
        await db.update_run_counts(run_id)
        await db.update_run_status(run_id, "completed")
    except asyncio.CancelledError:
        await db.update_run_counts(run_id)
        await db.update_run_status(run_id, "cancelled")
        raise


async def _scout(coro, account_id, step, label):
    await db.add_log(account_id, step, f"{label} running")
    result = await coro
    await db.add_log(account_id, step, f"{label} done")
    return result


async def process_account(
    run_id: int, account: dict, value_prop: str
) -> None:
    account_id = account["id"]
    try:
        await db.update_account(account_id, status="running")

        # === RESEARCH (parallel, no LLM) ===
        homepage, news_raw, linkedin_raw = await asyncio.gather(
            _scout(homepage_scout.run(account), account_id,
                   "homepage_scout", "Atlas · homepage scrape"),
            _scout(news_scout.run(account), account_id,
                   "news_scout", "Echo · news search"),
            _scout(linkedin_analyst.run(account), account_id,
                   "linkedin_analyst", "Talent · hiring search"),
        )
        await db.update_account(account_id, homepage=homepage)

        # === SIFT (distill signals) ===
        await db.add_log(account_id, "signal_extractor",
                         "Sift · distilling signals")
        signals = await signal_extractor.run(account, news_raw, linkedin_raw)
        await db.update_account(
            account_id,
            news=signals["news_signals"],
            linkedin=signals["linkedin_signals"],
        )
        await db.add_log(account_id, "signal_extractor", "Sift · signals ready")

        # === ORACLE (build hypothesis) — pass 1 ===
        await db.add_log(account_id, "hypothesis_builder",
                         "Oracle · building 1-page hypothesis")
        hypothesis_1 = await hypothesis_builder.run(
            account, value_prop, homepage, signals
        )
        await db.update_account(account_id, hypothesis_1=hypothesis_1)
        await db.add_log(account_id, "hypothesis_builder",
                         f"Oracle · angle '{hypothesis_1.get('angle', '')}'")

        # === VERDICT (score) — pass 1 ===
        await db.add_log(account_id, "scorer", "Verdict · scoring fit")
        eval_1 = await scorer.run(account, value_prop, hypothesis_1, signals)
        await db.update_account(account_id, eval_1=eval_1)
        await db.add_log(account_id, "scorer",
                         f"Verdict · score {eval_1.get('score')}/10")

        if eval_1.get("relevant"):
            await _finalise(
                account_id, account, value_prop,
                hypothesis_1, signals["news_signals"],
                signals["linkedin_signals"], eval_1,
            )
            return

        # === RETRY: Oracle + Verdict only (signals don't change) ===
        await db.add_log(
            account_id, "hypothesis_builder_pass_2",
            f"Oracle (retry) · score {eval_1.get('score')} < threshold, new angle",
        )
        await db.update_account(account_id, retry_count=1)
        previous = {"hypothesis": hypothesis_1, "evaluation": eval_1}
        hypothesis_2 = await hypothesis_builder.run(
            account, value_prop, homepage, signals, previous=previous
        )
        await db.update_account(account_id, hypothesis_2=hypothesis_2)
        await db.add_log(
            account_id, "hypothesis_builder_pass_2",
            f"Oracle (retry) · angle '{hypothesis_2.get('angle', '')}'",
        )

        await db.add_log(account_id, "scorer_pass_2",
                         "Verdict (retry) · scoring new angle")
        eval_2 = await scorer.run(account, value_prop, hypothesis_2, signals)
        await db.update_account(account_id, eval_2=eval_2)
        await db.add_log(account_id, "scorer_pass_2",
                         f"Verdict (retry) · score {eval_2.get('score')}/10")

        if eval_2.get("relevant"):
            await _finalise(
                account_id, account, value_prop,
                hypothesis_2, signals["news_signals"],
                signals["linkedin_signals"], eval_2,
            )
            return

        await db.add_log(
            account_id, "drop",
            f"Dropped — best score {eval_2.get('score')}",
        )
        await db.update_account(account_id, status="dropped")

    except asyncio.CancelledError:
        await db.update_account(
            account_id, status="error", error_message="cancelled"
        )
        raise
    except Exception as e:
        tb = traceback.format_exc(limit=2)
        await db.add_log(account_id, "error", f"{e}\n{tb}")
        await db.update_account(
            account_id, status="error", error_message=str(e)
        )


async def _finalise(
    account_id: int,
    account: dict,
    value_prop: str,
    hypothesis: dict,
    news: dict,
    linkedin: dict,
    evaluation: dict,
) -> None:
    await db.add_log(account_id, "outreach_angles", "Pitch · generating 12 angles")
    angles = await outreach_angles.run(account, value_prop, hypothesis)
    await db.update_account(account_id, outreach_angles=angles)
    await db.add_log(account_id, "outreach_angles",
                     f"Pitch · {len(angles.get('angles', []))} angles")

    await db.add_log(account_id, "linkedin_search", "Hunter · building search")
    search_commands = await linkedin_search.run(account, evaluation, linkedin)
    await db.update_account(account_id, search_commands=search_commands)
    await db.add_log(account_id, "linkedin_search", "Hunter · search ready")

    await db.add_log(account_id, "dossier", "Scribe · writing briefing")
    dossier = await dossier_compiler.run(
        account, hypothesis, news, linkedin, evaluation, search_commands,
        outreach_angles=angles,
    )
    await db.update_account(account_id, dossier=dossier)
    await db.add_log(account_id, "dossier", "Scribe · briefing ready")

    await pipedrive_writer(
        account_id, account, dossier, evaluation, search_commands
    )
    await db.update_account(account_id, status="enriched")


async def pipedrive_writer(
    account_id: int,
    account: dict,
    dossier: dict,
    evaluation: dict,
    search_commands: dict,
) -> None:
    await db.add_log(account_id, "pipedrive", "Ledger · writing to Pipedrive")
    try:
        org_id = await pipedrive.find_or_create_org(account["name"])
        note_id = await pipedrive.add_note(
            org_id, dossier.get("pipedrive_note", "")
        )
        await pipedrive.add_label(
            org_id, f"enriched-score-{evaluation.get('score', 0)}"
        )
        await db.update_account(
            account_id,
            pipedrive_org_id=org_id,
            pipedrive_note_id=note_id,
        )
        await db.add_log(
            account_id, "pipedrive", f"Ledger · org {org_id} note {note_id}"
        )
    except Exception as e:
        await db.add_log(account_id, "error", f"Pipedrive write failed: {e}")
        await db.update_account(
            account_id, pipedrive_org_id=None, pipedrive_note_id=None
        )
