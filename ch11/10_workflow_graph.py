"""Samples 8-1, 8-2, 11-2, and 12-2: graph workflows and checkpoints."""

import asyncio
from dataclasses import dataclass

from agent_framework import (
    Agent,
    Executor,
    InMemoryCheckpointStorage,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
)

from sample_support import ScriptedChatClient, open_client, parse_args


@dataclass
class EventProposal:
    participants: int
    budget: int


# %% SAMPLE START: 11 - Decorator executor
@executor(id="positive_number")
async def positive_number(
    input_number: int,
    ctx: WorkflowContext[bool, str],
) -> None:
    await ctx.send_message(input_number > 0)
    await ctx.yield_output(str(input_number))
# %% SAMPLE END


# %% SAMPLE START: 16 - Graph workflow state across executors
@executor(id="accumulate")
async def accumulate(
    value: int,
    ctx: WorkflowContext[str],
) -> None:
    total = ctx.get_state("total", 0) + value
    ctx.set_state("total", total)
    await ctx.send_message("total")


@executor(id="read_total")
async def read_total(key: str, ctx: WorkflowContext[None, int]) -> None:
    await ctx.yield_output(ctx.get_state(key))
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

        # %% SAMPLE START: 12 - Class executor graph workflow
        class BudgetCheck(Executor):
            @handler
            async def check(
                self,
                proposal: EventProposal,
                context: WorkflowContext[Message, str],
            ) -> None:
                cost = 5_000 + proposal.participants * 800
                if cost > proposal.budget:
                    await context.yield_output("Rejected: over budget.")
                else:
                    await context.send_message(
                        Message("user", [
                            f"Plan an event for {proposal.participants} people costing {cost} JPY."
                        ])
                    )

        budget_check = BudgetCheck(id="budget_check")
        event_workflow = (
            WorkflowBuilder(start_executor=budget_check, output_from=[budget_check, reviewer])
            .add_edge(budget_check, writer)
            .add_edge(writer, reviewer)
            .build()
        )
        # %% SAMPLE END

        result = await event_workflow.run(EventProposal(participants=24, budget=30_000))
        rejected = await event_workflow.run(EventProposal(participants=24, budget=10_000))
        assert len(result.get_outputs()) == 1
        assert result.get_outputs()[0].text.strip()
        assert rejected.get_outputs() == ["Rejected: over budget."]
        if args.offline:
            assert isinstance(client, ScriptedChatClient)
            assert replies[-1] in result.get_outputs()[0].text
            assert len(client.requests) == 2
            assert any(replies[0] in message.text for message in client.requests[1])

    signs = []
    @executor(id="record_sign")
    async def record_sign(sign: bool, ctx: WorkflowContext[None, bool]) -> None:
        signs.append(sign)
        await ctx.yield_output(sign)

    decorator_workflow = (
        WorkflowBuilder(start_executor=positive_number, output_from=[positive_number, record_sign])
        .add_edge(positive_number, record_sign)
        .build()
    )
    for number in (7, 0, -2):
        decorator_result = await decorator_workflow.run(number)
        assert decorator_result.get_outputs() == [str(number), number > 0]
    assert signs == [True, False, False]

    state_workflow = (
        WorkflowBuilder(start_executor=accumulate, output_from=[read_total])
        .add_edge(accumulate, read_total)
        .build()
    )
    first_state = await state_workflow.run(4)
    second_state = await state_workflow.run(5)
    assert first_state.get_outputs() == [4]
    assert second_state.get_outputs() == [9]

    # %% SAMPLE START: 18 - Builder checkpoint storage
    builder_storage = InMemoryCheckpointStorage()
    builder = (
        WorkflowBuilder(
            name="total_workflow",
            start_executor=accumulate,
            output_from=[read_total],
            checkpoint_storage=builder_storage,
        )
        .add_edge(accumulate, read_total)
    )
    builder_checkpointed = builder.build()
    # %% SAMPLE END

    # %% SAMPLE START: 18 - Build-time storage and restoration
    builder_result = await builder_checkpointed.run(6)
    checkpoints = await builder_storage.list_checkpoints(workflow_name=builder_checkpointed.name)
    checkpoint = next(saved for saved in checkpoints if saved.iteration_count == 1)
    builder_restored = builder.build()
    builder_resumed = await builder_restored.run(checkpoint_id=checkpoint.checkpoint_id)
    # %% SAMPLE END

    assert builder_result.get_outputs() == [6]
    assert builder_resumed.get_outputs() == [6]
    assert checkpoint.state["total"] == 6

    # %% SAMPLE START: 18 - Runtime storage and restoration
    runtime_builder = (
        WorkflowBuilder(name="total_workflow", start_executor=accumulate, output_from=[read_total])
        .add_edge(accumulate, read_total)
    )
    runtime_checkpointed = runtime_builder.build()
    runtime_storage = InMemoryCheckpointStorage()
    runtime_result = await runtime_checkpointed.run(
        8,
        checkpoint_storage=runtime_storage,
    )
    checkpoints = await runtime_storage.list_checkpoints(workflow_name=runtime_checkpointed.name)
    checkpoint = next(saved for saved in checkpoints if saved.iteration_count == 1)
    runtime_restored = runtime_builder.build()
    restored = await runtime_restored.run(
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_storage=runtime_storage,
    )
    # %% SAMPLE END

    assert runtime_result.get_outputs() == [8]
    assert restored.get_outputs() == [8]
    assert checkpoint.state["total"] == 8
    print(result.get_outputs()[0].text)
    print("PASS: decorator/class executors, persistent graph state, and checkpoint options")


if __name__ == "__main__":
    asyncio.run(main())
