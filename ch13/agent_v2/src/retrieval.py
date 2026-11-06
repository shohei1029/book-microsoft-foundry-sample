from azure.core.credentials_async import AsyncTokenCredential
from azure.search.documents import ApiVersion
from azure.search.documents.knowledgebases.aio import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import (
    KnowledgeBaseMessage,
    KnowledgeBaseMessageTextContent,
    KnowledgeBaseRetrievalRequest,
    KnowledgeRetrievalLowReasoningEffort,
    SearchIndexKnowledgeSourceParams,
)


class FoundryIQRetriever:
    def __init__(
        self,
        credential: AsyncTokenCredential,
        endpoint: str,
        knowledge_base_name: str,
        knowledge_source_name: str,
    ) -> None:
        self.client = KnowledgeBaseRetrievalClient(
            endpoint=endpoint.rstrip("/"),
            credential=credential,
            knowledge_base_name=knowledge_base_name,
            api_version=ApiVersion.V2026_08_01_PREVIEW,
            connection_timeout=120,
            read_timeout=120,
            retry_total=0,
        )
        self.knowledge_source_name = knowledge_source_name

    async def retrieve(self, query: str) -> dict:
        if not query.strip():
            raise ValueError("Foundry IQ retrieval requires a non-empty query.")
        response = await self.client.retrieve(
            KnowledgeBaseRetrievalRequest(
                messages=[
                    KnowledgeBaseMessage(
                        role="user",
                        content=[KnowledgeBaseMessageTextContent(text=query)],
                    )
                ],
                retrieval_reasoning_effort=KnowledgeRetrievalLowReasoningEffort(),
                knowledge_source_params=[
                    SearchIndexKnowledgeSourceParams(
                        knowledge_source_name=self.knowledge_source_name,
                        include_references=True,
                        include_reference_source_data=True,
                    )
                ],
            )
        )
        result = response.as_dict()
        try:
            answer = result["response"][0]["content"][0]["text"]
            references = result["references"]
            if not isinstance(answer, str) or not isinstance(references, list):
                raise TypeError("Foundry IQ answer/references have invalid types.")
            sources = []
            for reference in references:
                source = reference.get("sourceData")
                if source is None:
                    continue
                sources.append(
                    {
                        "ref_id": str(reference["id"]),
                        "title": source["title"],
                        "content": source["chunk"],
                    }
                )
                if not all(
                    isinstance(sources[-1][key], str) for key in ("title", "content")
                ):
                    raise ValueError("Foundry IQ source title/chunk must be strings.")
        except (KeyError, IndexError, TypeError, AttributeError) as error:
            raise ValueError(
                "Foundry IQ returned an unexpected response shape."
            ) from error
        return {
            "query": query,
            "answer": answer,
            "sources": sources,
            "raw_response": result,
        }

    async def close(self) -> None:
        await self.client.close()
