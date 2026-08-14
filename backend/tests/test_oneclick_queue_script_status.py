from __future__ import annotations

from types import SimpleNamespace

from app.services import oneclick_service


def test_queue_script_status_uses_pipeline_loader_without_changing_queue(monkeypatch):
    original_queue = {
        "channel_presets": {"5": "silla-preset"},
        "items": [
            {
                "id": "silla-ep02",
                "channel": 5,
                "topic": "신라 EP02",
                "episode_number": 2,
                "episode_code": "SILLA_EP02",
                "target_cuts": 150,
            },
            {
                "id": "silla-ep03",
                "channel": 5,
                "topic": "신라 EP03",
                "episode_number": 3,
                "episode_code": "SILLA_EP03",
                "target_cuts": 150,
            },
        ],
    }
    monkeypatch.setattr(oneclick_service, "_STATE_LOADED", True)
    monkeypatch.setattr(oneclick_service, "_QUEUE", original_queue)
    monkeypatch.setattr(
        oneclick_service,
        "_load_project",
        lambda project_id: SimpleNamespace(id=project_id, config={"channel": 5}),
    )

    calls = []

    def fake_load(project_id, config, topic):
        calls.append((project_id, dict(config), topic))
        if config.get("episode_code") == "SILLA_EP02":
            return {"cuts": [{}] * 150}, r"C:\prepared_scripts\SILLA_EP02_script.json"
        return None

    monkeypatch.setattr(oneclick_service, "_load_prepared_script", fake_load)

    result = oneclick_service.get_queue_script_status()

    assert result["items"][0]["registered"] is True
    assert result["items"][0]["source_name"] == "SILLA_EP02_script.json"
    assert result["items"][1]["registered"] is False
    assert calls[0][0] == "silla-preset"
    assert calls[0][1]["episode_number"] == 2
    assert calls[0][1]["episode_code"] == "SILLA_EP02"
    assert calls[0][1]["target_cuts"] == 150
    assert original_queue["items"][0].get("registered") is None


def test_queue_script_status_reports_missing_preset_without_loading(monkeypatch):
    monkeypatch.setattr(oneclick_service, "_STATE_LOADED", True)
    monkeypatch.setattr(
        oneclick_service,
        "_QUEUE",
        {"channel_presets": {}, "items": [{"id": "ep01", "channel": 8, "topic": "EP01"}]},
    )
    monkeypatch.setattr(
        oneclick_service,
        "_load_prepared_script",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not load")),
    )

    result = oneclick_service.get_queue_script_status()

    assert result == {
        "items": [
            {
                "item_id": "ep01",
                "registered": False,
                "preset_id": None,
                "source_name": None,
                "reason": "preset_missing",
            }
        ]
    }
