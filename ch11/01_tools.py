"""Sample 1: define and invoke a FunctionTool with the tool decorator."""

import asyncio

from agent_framework import tool

from sample_support import check_environment


# %% SAMPLE START: 1 - tool decorator
@tool(
    name="estimate_event_cost",
    description="Estimate the event cost in JPY from the participant count.",
    approval_mode="never_require",
)
def estimate_event_cost(participants: int) -> int:
    return 5_000 + participants * 800
# %% SAMPLE END


async def main():
    check_environment()
    result = await estimate_event_cost.invoke(arguments={"participants": 24})
    assert result and result[0].text == "24200"
    assert estimate_event_cost.name == "estimate_event_cost"
    assert estimate_event_cost.approval_mode == "never_require"
    print(result[0].text)
    print("PASS: @tool metadata, schema validation, and invocation")


if __name__ == "__main__":
    asyncio.run(main())
