"""Samples 14-1, 14-2, and 15: equivalent decorator/class middleware."""

import asyncio
import logging

from agent_framework import (
    Agent,
    AgentContext,
    AgentMiddleware,
    ChatContext,
    ChatMiddleware,
    Content,
    FunctionInvocationContext,
    FunctionMiddleware,
    MiddlewareFailure,
    agent_middleware,
    chat_middleware,
    function_middleware,
)

from sample_support import open_client, parse_args

logger = logging.getLogger("middleware_sample")
logger.setLevel(logging.INFO)
logger.propagate = False
events = []
tool_attempts = 0
failures_left = 1


class EventLog(logging.Handler):
    def emit(self, record):
        events.append(record.getMessage())
        print(record.getMessage())


logger.addHandler(EventLog())


async def get_room_capacity() -> int:
    """Return capacity from a read-only room service."""
    global tool_attempts, failures_left
    tool_attempts += 1
    logger.info("tool.call")
    if failures_left:
        failures_left -= 1
        raise TimeoutError("Injected transient read failure.")
    return 30


# %% SAMPLE START: 20 - Decorator middleware definitions
@agent_middleware
async def log_agent(context: AgentContext, call_next):
    logger.info("agent.before")
    try:
        await call_next()
    finally:
        logger.info("agent.after")


@chat_middleware
async def log_chat(context: ChatContext, call_next):
    logger.info("chat.before")
    try:
        await call_next()
    finally:
        logger.info("chat.after")


@function_middleware
async def log_function(context: FunctionInvocationContext, call_next):
    logger.info("function.before")
    try:
        await call_next()
    finally:
        logger.info("function.after")


@function_middleware
async def retry_read(context: FunctionInvocationContext, call_next):
    for attempt in range(1, 4):
        logger.info("retry.attempt.%s", attempt)
        try:
            await call_next()
            return
        except TimeoutError as error:
            if attempt == 3:
                raise MiddlewareFailure("Read failed after three attempts.") from error
            logger.info("retry.timeout")
            await asyncio.sleep(0.1 * 2 ** (attempt - 1))
# %% SAMPLE END


# %% SAMPLE START: 21 - Class middleware definitions
class LogAgent(AgentMiddleware):
    async def process(self, context: AgentContext, call_next):
        logger.info("agent.before")
        try:
            await call_next()
        finally:
            logger.info("agent.after")


class LogChat(ChatMiddleware):
    async def process(self, context: ChatContext, call_next):
        logger.info("chat.before")
        try:
            await call_next()
        finally:
            logger.info("chat.after")


class LogFunction(FunctionMiddleware):
    async def process(self, context: FunctionInvocationContext, call_next):
        logger.info("function.before")
        try:
            await call_next()
        finally:
            logger.info("function.after")


class RetryRead(FunctionMiddleware):
    async def process(self, context: FunctionInvocationContext, call_next):
        for attempt in range(1, 4):
            logger.info("retry.attempt.%s", attempt)
            try:
                await call_next()
                return
            except TimeoutError as error:
                if attempt == 3:
                    raise MiddlewareFailure("Read failed after three attempts.") from error
                logger.info("retry.timeout")
                await asyncio.sleep(0.1 * 2 ** (attempt - 1))
# %% SAMPLE END


async def verify_agent(agent, client, *, offline):
    global failures_left, tool_attempts
    failures_left, tool_attempts = 1, 0
    events.clear()
    result = await agent.run("What is the room capacity?")
    assert "30" in result.text
    expected = [
        "agent.before", "chat.before", "chat.after", "function.before",
        "retry.attempt.1", "tool.call", "retry.timeout", "retry.attempt.2",
        "tool.call", "function.after", "chat.before", "chat.after", "agent.after",
    ]
    if offline:
        assert events == expected, events
        assert tool_attempts == 2
    else:
        assert events[0] == "agent.before" and events[-1] == "agent.after"
        assert events.index("function.before") < events.index("retry.attempt.1")
        assert "retry.timeout" in events
    print(result.text)
    if offline:
        client.replies = iter([
            [Content.from_function_call("capacity-2", "get_room_capacity", arguments={})],
        ])
        events.clear()
        tool_attempts, failures_left = 0, 10
        try:
            await agent.run("What is the room capacity?")
        except MiddlewareFailure:
            assert tool_attempts == 3
            assert events[-2:] == ["function.after", "agent.after"]
        else:
            raise AssertionError("Retry exhaustion must fail the run.")


async def main():
    args = parse_args(__doc__)
    tool_request = [Content.from_function_call("capacity-1", "get_room_capacity", arguments={})]
    async with open_client(args, [tool_request, "The room holds 30 people."]) as client:
        # %% SAMPLE START: 22 - Decorator middleware registration
        agent = Agent(
            client=client,
            instructions="Call get_room_capacity once, then report the returned capacity.",
            tools=[get_room_capacity],
            middleware=[log_agent, log_chat, log_function, retry_read],
            default_options={"store": False},
        )
        # %% SAMPLE END
        await verify_agent(agent, client, offline=args.offline)
        print("PASS: decorator middleware order and bounded retry")

    async with open_client(args, [tool_request, "The room holds 30 people."]) as client:
        # %% SAMPLE START: 23 - Class middleware registration
        agent = Agent(
            client=client,
            instructions="Call get_room_capacity once, then report the returned capacity.",
            tools=[get_room_capacity],
            middleware=[LogAgent(), LogChat(), LogFunction(), RetryRead()],
            default_options={"store": False},
        )
        # %% SAMPLE END
        await verify_agent(agent, client, offline=args.offline)
        print("PASS: class middleware has the same order and bounded retry")


if __name__ == "__main__":
    asyncio.run(main())
