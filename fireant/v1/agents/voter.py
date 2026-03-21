import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from .base import BaseAgent
from ..utils.manifest import (
    STANDARD_FILES,
    load_manifest,
    save_manifest,
    update_status,
)

logger = logging.getLogger("fireant")


class VoterAgent(BaseAgent):
    """Evaluates competing parallel approaches and selects the best one.

    Trigger: A manifest.json entry with mode "parallel" where at least one
             candidate has status_pass.flag, OR all candidates have terminated.
    Action:  Scores passing candidates on correctness, quality, performance,
             simplicity. Writes vote_result.json, promotes winner, prunes losers.
    """

    role = "voter"

    def check_trigger(self, directory: Path) -> bool:
        parallel = self.get_parallel(directory)
        for deliverable in parallel:
            candidates = deliverable.get("candidates", [])
            if not candidates:
                continue
            if self._candidates_ready(directory, candidates):
                return True
        return False

    def execute(self, directory: Path) -> None:
        manifest = self.read_manifest(directory)
        if manifest is None:
            return

        for deliverable in manifest["deliverables"]:
            if deliverable.get("mode") != "parallel":
                continue
            candidates = deliverable.get("candidates", [])
            if not candidates:
                continue
            if not self._candidates_ready(directory, candidates):
                continue

            passing = self._get_passing_candidates(directory, candidates)
            all_done = self._all_candidates_terminated(directory, candidates)

            if not passing and all_done:
                deliverable["status"] = "blocked"
                save_manifest(directory, manifest)
                self.write_escalation(directory, (
                    f"# Escalation: {deliverable['name']}\n\n"
                    f"All {len(candidates)} parallel candidates failed.\n"
                    f"Candidates: {', '.join(candidates)}\n"
                ))
                logger.warning(f"[voter] All candidates failed for '{deliverable['name']}' in {directory}")
                continue

            winner = self._vote(directory, deliverable["name"], passing)

            vote_result = {
                "deliverable": deliverable["name"],
                "candidates_evaluated": len(passing),
                "winner": winner["name"],
                "scores": winner["scores"],
                "reasoning": winner["reasoning"],
            }
            self.write_vote_result(directory, json.dumps(vote_result, indent=2))

            self._promote_winner(directory, deliverable, winner["name"], candidates, manifest)

        save_manifest(directory, manifest)

    # ── Candidate checks ─────────────────────────────────────────────

    def _candidates_ready(self, directory: Path, candidates: list[str]) -> bool:
        """At least one passed, or all terminated."""
        has_pass = any(self.has_status_pass(directory / c) for c in candidates)
        all_done = self._all_candidates_terminated(directory, candidates)
        return has_pass or all_done

    def _all_candidates_terminated(self, directory: Path, candidates: list[str]) -> bool:
        for c in candidates:
            cdir = directory / c
            if not cdir.exists():
                continue
            if self.has_status_pass(cdir):
                continue
            if self.has_escalation(cdir):
                continue
            cmanifest = self.read_manifest(cdir)
            if cmanifest:
                statuses = {d["status"] for d in cmanifest.get("deliverables", [])}
                if statuses - {"pass", "blocked", "fail"}:
                    return False
            else:
                return False
        return True

    def _get_passing_candidates(self, directory: Path, candidates: list[str]) -> list[str]:
        return [c for c in candidates if self.has_status_pass(directory / c)]

    # ── Voting ───────────────────────────────────────────────────────

    def _vote(self, directory: Path, deliverable_name: str, passing: list[str]) -> dict:
        """Evaluate passing candidates and pick the best."""
        if len(passing) == 1:
            return {
                "name": passing[0],
                "scores": {"sole_candidate": True},
                "reasoning": "Only one candidate passed — selected by default.",
            }

        candidate_summaries = []
        for c in passing:
            cdir = directory / c
            code_files = self.get_code_files(cdir)
            code_summary = {}
            for cf in code_files:
                content = cf.read_text()
                code_summary[cf.name] = content[:2000]
            candidate_summaries.append({
                "name": c,
                "files": code_summary,
            })

        prd = self.read_prd(directory) or ""

        prompt = (
            f"You are evaluating {len(passing)} competing implementations for '{deliverable_name}'.\n\n"
            "Score each candidate on a 1-10 scale for:\n"
            "1. Correctness — does it satisfy the PRD?\n"
            "2. Code quality — readability, maintainability\n"
            "3. Performance — efficiency\n"
            "4. Simplicity — fewer lines, fewer dependencies\n\n"
            "Return a JSON object with:\n"
            "- \"winner\": the candidate name\n"
            "- \"scores\": {candidate_name: {correctness, quality, performance, simplicity, total}}\n"
            "- \"reasoning\": explanation of the choice\n"
        )

        context = f"PRD:\n{prd}\n\nCandidates:\n{json.dumps(candidate_summaries, indent=2)}"

        raw = self.llm.generate_json(prompt, context=context)
        try:
            result = json.loads(raw)
            return {
                "name": result.get("winner", passing[0]),
                "scores": result.get("scores", {}),
                "reasoning": result.get("reasoning", ""),
            }
        except json.JSONDecodeError:
            logger.error(f"[voter] Failed to parse vote JSON, defaulting to first candidate")
            return {
                "name": passing[0],
                "scores": {"parse_error": True},
                "reasoning": "JSON parse error — selected first passing candidate.",
            }

    # ── Promote and prune ────────────────────────────────────────────

    def _promote_winner(
        self,
        directory: Path,
        deliverable: dict,
        winner_name: str,
        candidates: list[str],
        manifest: dict,
    ) -> None:
        """Rename winner to canonical name, remove losers."""
        canonical_name = deliverable["name"]
        winner_dir = directory / winner_name
        canonical_dir = directory / canonical_name

        if canonical_dir.exists() and canonical_dir != winner_dir:
            shutil.rmtree(canonical_dir)

        if winner_dir.exists() and winner_name != canonical_name:
            winner_dir.rename(canonical_dir)

        for c in candidates:
            if c == winner_name:
                continue
            loser_dir = directory / c
            if loser_dir.exists():
                shutil.rmtree(loser_dir)

        deliverable["status"] = "pass"
        deliverable["mode"] = "single"
        deliverable["candidates"] = []

        logger.info(
            f"[voter] Promoted '{winner_name}' → '{canonical_name}' in {directory}, "
            f"pruned {len(candidates) - 1} losers"
        )
