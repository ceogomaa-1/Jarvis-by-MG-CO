import pytest

from backend.lib.business.operator import creator


@pytest.mark.asyncio
async def test_run_creator_batches_moves_and_preserves_move_order(monkeypatch):
    monkeypatch.setattr(creator, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("JARVIS_OPERATOR_CREATOR_BATCH", "1")
    monkeypatch.setenv("JARVIS_OPERATOR_CREATOR_BATCH_MIN", "2")
    monkeypatch.setenv("JARVIS_OPERATOR_CREATOR_ADVISOR", "0")

    captured_requests = []

    async def fake_run_message_batch(requests, **kwargs):
        captured_requests.extend(requests)
        assert kwargs["beta_headers"] == []
        # Anthropic does not guarantee result ordering, so return these reversed.
        return {"id": "msgbatch_test"}, [
            {
                "custom_id": requests[1]["custom_id"],
                "result": {
                    "type": "succeeded",
                    "message": {"content": [{"type": "text", "text": "Artifact for m2"}]},
                },
            },
            {
                "custom_id": requests[0]["custom_id"],
                "result": {
                    "type": "succeeded",
                    "message": {"content": [{"type": "text", "text": "Artifact for m1"}]},
                },
            },
        ]

    monkeypatch.setattr(creator, "run_message_batch", fake_run_message_batch)

    result = await creator.run_creator(
        strategist_plan={
            "moves": [
                {"id": "m1", "title": "Move One", "preparation_type": "campaign", "sub_agent_brief": "Draft one."},
                {"id": "m2", "title": "Move Two", "preparation_type": "analysis", "sub_agent_brief": "Draft two."},
            ]
        },
        researcher_output={"research": {}},
        industry="dental",
        business_name="Jarvis Dental",
        north_star_label="$1M ARR",
        connector_summary="No connectors",
        max_parallel=6,
    )

    assert len(captured_requests) == 2
    assert captured_requests[0]["params"]["model"] == creator.MODEL
    assert [r["move_id"] for r in result] == ["m1", "m2"]
    assert [r["artifact"] for r in result] == ["Artifact for m1", "Artifact for m2"]
    assert all(r["billing_mode"] == "batch" for r in result)
    assert all(r["batch_id"] == "msgbatch_test" for r in result)
