"""Prompt management with hierarchical model-specific overrides."""

import os
from pathlib import Path
from typing import Any

from answer_eval.core.errors import ConfigurationError
from answer_eval.core.logging import get_logger
from answer_eval.models.profiles import ModelProfile

logger = get_logger("prompts.manager")


class PromptManager:
    """Manages prompt template loading with model-family and model-size overrides."""

    def __init__(
        self,
        templates_dir: Path | str | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        self.workspace_root = workspace_root or Path(os.getcwd())
        if templates_dir is None:
            self.templates_dir = self.workspace_root / "src" / "answer_eval" / "prompts" / "templates"
        else:
            self.templates_dir = Path(templates_dir)

    def get_prompt_template(
        self,
        task: str,
        model: ModelProfile | None = None,
    ) -> str:
        """
        Load prompt template for a specific task (e.g. 'ocr', 'diagram', 'segmentation').
        Resolution order:
        1. templates/{task}/{family}_{size_class}.txt
        2. templates/{task}/{family}.txt
        3. templates/{task}/base.txt
        """
        task_dir = self.templates_dir / task
        if not task_dir.exists():
            raise ConfigurationError(f"Prompt templates task directory '{task}' not found at: {task_dir}")

        candidates: list[Path] = []
        if model is not None:
            candidates.append(task_dir / f"{model.family}_{model.size_class}.txt")
            candidates.append(task_dir / f"{model.family}.txt")

        candidates.append(task_dir / "base.txt")

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                logger.debug("Resolved prompt template", task=task, template_file=candidate.name)
                with open(candidate, encoding="utf-8") as f:
                    return f.read().strip()

        raise ConfigurationError(
            f"No valid prompt template found for task '{task}' in {task_dir}. Looked for: {[c.name for c in candidates]}"
        )

    def render_prompt(
        self,
        task: str,
        model: ModelProfile | None = None,
        **kwargs: Any,
    ) -> str:
        """Load template and render with format variables."""
        template = self.get_prompt_template(task, model=model)
        if kwargs:
            try:
                return template.format(**kwargs)
            except KeyError as e:
                logger.warning(
                    "Missing variable in prompt rendering",
                    task=task,
                    missing_key=str(e),
                )
        return template
