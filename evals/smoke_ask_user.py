"""No-network smoke checks for structured user clarification."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from execution.skill_executor import SkillExecutor
from registries.skill_registry import list_skill_names
from registries.tool_registry import get_tool, list_tool_names


def main() -> int:
    assert "ask_user" in list_skill_names()
    assert "ask_user" in list_tool_names()

    tool = get_tool("ask_user")
    assert tool.category == "interaction"
    result = tool.run(
        {
            "question": "Which database should I search?",
            "options": ["UniProt", "NCBI"],
        }
    )
    assert result == {
        "status": "awaiting_user_input",
        "needs_input": True,
        "question": "Which database should I search?",
        "options": ["UniProt", "NCBI"],
        "other_label": "Other",
        "summary": "Waiting for the user to choose an option or provide another answer.",
    }

    record = SkillExecutor().execute_skill(
        "ask_user",
        {
            "question": "Which sequence type do you have?",
            "options": ["DNA", "RNA"],
            "other_label": "A different type",
        },
    )
    assert record["result"]["needs_input"] is True
    assert record["tool_calls"][0]["tool"] == "ask_user"

    try:
        tool.run(
            {
                "question": "Invalid options?",
                "options": ["Other", "NCBI"],
            }
        )
    except ValueError as exc:
        assert "other_label" in str(exc)
    else:
        raise AssertionError("Expected duplicate Other option to be rejected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
