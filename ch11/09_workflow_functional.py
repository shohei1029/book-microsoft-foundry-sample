"""Samples 7, 11-1, 12-1, and 13: functional workflows, state, and checkpoints."""

import asyncio
from dataclasses import dataclass

from agent_framework import (
    Agent,
    InMemoryCheckpointStorage,
    RunContext,
    step,
    workflow,
)

from sample_support import ScriptedChatClient, open_client, parse_args


@dataclass
class EventProposal:
    participants: int
    budget: int


# %% SAMPLE START: 15 - Functional workflow state
@workflow(name="running_total")
async def update_total(value: int, ctx: RunContext) -> int:
    total = ctx.get_state("total", 0) + value
    ctx.set_state("total", total)
    return ctx.get_state("total")
# %% SAMPLE END


prepared = []


@step
async def prepare(message: str) -> str:
    prepared.append(message)
    return message.upper()


# %% SAMPLE START: 17 - Checkpoint-enabled functional workflow
@workflow(name="approval_workflow")
async def approval_workflow(message: str, ctx: RunContext) -> str:
    draft = await prepare(message)
    approved = await ctx.request_info(
        draft, response_type=bool, request_id="approval",
    )
    return draft if approved else "Rejected."


storage = InMemoryCheckpointStorage()
checkpointed_workflow = approval_workflow.build(checkpoint_storage=storage)
# %% SAMPLE END


async def main():
    args = parse_args(__doc__)
    replies = ["Draft: a short workshop for 24 people.", "Reviewed: workshop for 24 people."]
    async with open_client(args, replies) as client:
        writer = Agent(
            client=client,
            name="writer",
            instructions="Draft an internal event plan in at most three sentences.",
            default_options={"store": False},
        )
        reviewer = Agent(
            client=client,
            name="reviewer",
            instructions="Review the draft and return only the improved plan.",
            default_options={"store": False},
        )

        # %% SAMPLE START: 10 - Functional workflow
        @step
        async def estimate_cost(proposal: EventProposal) -> int:
            return 5_000 + proposal.participants * 800

        @workflow
        async def plan_event(proposal: EventProposal) -> str:
            cost = await estimate_cost(proposal)
            if cost > proposal.budget:
                return "Rejected: over budget."
            brief = f"Plan an event for {proposal.participants} people costing {cost} JPY."
            draft = await writer.run(brief)
            review = await reviewer.run(draft.text)
            return review.text

        event_workflow = plan_event.build()
        # %% SAMPLE END

        result = await event_workflow.run(EventProposal(participants=24, budget=30_000))
        rejected = await plan_event.build().run(EventProposal(participants=24, budget=10_000))
        assert len(result.get_outputs()) == 1
        assert result.get_outputs()[0].strip()
        assert rejected.get_outputs() == ["Rejected: over budget."]
        if args.offline:
            assert isinstance(client, ScriptedChatClient)
            assert result.get_outputs() == [replies[-1]]
            assert len(client.requests) == 2
            assert any(replies[0] in message.text for message in client.requests[1])

    state_workflow = update_total.build()
    first_state_run = await state_workflow.run(3)
    second_state_run = await state_workflow.run(4)
    assert first_state_run.get_outputs() == [3]
    assert second_state_run.get_outputs() == [4]

    initial = await checkpointed_workflow.run("event plan")
    assert initial.get_outputs() == []
    assert len(initial.get_request_info_events()) == 1
    assert prepared == ["event plan"]

    checkpoint = await storage.get_latest(workflow_name=checkpointed_workflow.name)
    assert checkpoint is not None

    # %% SAMPLE START: 19 - Resume from checkpoint on a fresh instance
    restored_workflow = approval_workflow.build(checkpoint_storage=storage)
    resumed = await restored_workflow.run(
        checkpoint_id=checkpoint.checkpoint_id,
        responses={"approval": True},
    )
    # %% SAMPLE END

    assert resumed.get_outputs() == ["EVENT PLAN"]
    assert prepared == ["event plan"], "The completed @step must not execute again on replay."
    print(result.get_outputs()[0])
    print("PASS: functional workflow, isolated state, checkpoint save, and resume")


if __name__ == "__main__":
    asyncio.run(main())
