from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.services import oneclick_service


def test_factory_v5_oneclick_voice_step_uses_pipeline_voice_logic():
    project = MagicMock()
    project.config = {"factory_version": 5}
    project.step_states = {"3": "running"}
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = project

    with (
        patch.object(oneclick_service, "SessionLocal", return_value=db),
        patch("app.tasks.pipeline_tasks._step_voice") as step_voice,
    ):
        asyncio.run(oneclick_service._start_studio_router_step("factory-project", 3))

    step_voice.assert_called_once_with("factory-project", {"factory_version": 5})
    assert project.step_states["3"] == "completed"
    db.commit.assert_called_once()
    db.close.assert_called_once()
