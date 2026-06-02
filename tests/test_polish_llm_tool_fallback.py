"""润色 LLM：tool 400 时回退 json_object。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from backend.app.llm_service import _polish_llm_call


def test_polish_llm_call_falls_back_to_json_on_tool_400() -> None:
    db = MagicMock()
    err_resp = MagicMock()
    err_resp.status_code = 400
    tool_err = httpx.HTTPStatusError("bad", request=MagicMock(), response=err_resp)

    with patch("backend.app.llm_service.chat_completion") as mock_cc:
        mock_cc.side_effect = [tool_err, ("{\"title\":\"t\"}", 1, 2, {})]
        raw, payload = _polish_llm_call(
            db,
            system="s",
            user="u",
            ref_id="r1",
            response_json=False,
            use_tool=True,
        )
    assert payload is None
    assert "title" in raw
    assert mock_cc.call_count == 2
    assert mock_cc.call_args_list[1].kwargs.get("response_json") is True
