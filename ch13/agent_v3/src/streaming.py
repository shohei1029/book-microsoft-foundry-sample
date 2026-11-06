from collections.abc import Awaitable
from typing import Any

from agent_framework import AgentResponse, AgentResponseUpdate, ResponseStream


AgentStream = ResponseStream[AgentResponseUpdate, AgentResponse[Any]]


async def completed_stream(pending: Awaitable[AgentResponse[Any]]) -> AgentStream:
    response = await pending

    async def updates():
        for message in response.messages:
            yield AgentResponseUpdate(
                contents=message.contents,
                role=message.role,
                author_name=message.author_name,
                agent_id=response.agent_id,
                response_id=response.response_id,
            )

    return ResponseStream(updates(), finalizer=lambda _: response)
