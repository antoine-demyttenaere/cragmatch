from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnablePassthrough

# Same grounding rule as REASONS_PROMPT in rag/reasons.py: only the
# retrieved text, no facts from the model's own knowledge.
RAG_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You recommend climbing sectors. Answer using ONLY the sectors below; "
            "do not add facts from your own knowledge about these places. "
            "Name the sectors you recommend. If none of them fit, say so.\n\n"
            "Sectors:\n{context}",
        ),
        ("human", "{question}"),
    ]
)


def format_docs(docs: list[Document]) -> str:
    # An empty list gives "": no result is a normal answer, the prompt handles it.
    return "\n\n".join(doc.page_content for doc in docs)


def build_rag_chain(retriever: Runnable, llm: Runnable) -> Runnable:
    # Typed as Runnable (not the concrete classes) so tests can pass fakes.
    return (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | RAG_PROMPT
        | llm
        | StrOutputParser()
    )
