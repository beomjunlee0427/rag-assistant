from src.rag.retriever import (
    load_vector_store,
    get_retriever,
    build_context,
    expand_related_appendices,
)

from src.rag.ingest import (
    chroma_exists,
    create_vector_store,
    get_embeddings,
)

from src.rag.rag_chain import (
    create_rag_chain,
)

from src.rag.query_rewriter import (
    rewrite_query,
    format_chat_history,
)

from src.rag.source import (
    build_sources,
)


# =========================================================
# RAG 초기화
# =========================================================

def initialize_rag(
    embeddings=None,
):

    if embeddings is None:
        embeddings = get_embeddings()

    # Chroma가 있으면 기존 DB 사용
    if chroma_exists():

        try:

            vector_store = load_vector_store(
                embeddings=embeddings,
            )

        except Exception:

            # DB 파일이 깨졌거나 collection 문제가 있을 경우
            # 다시 생성
            vector_store = create_vector_store(
                embeddings=embeddings,
            )

    # Chroma가 없으면 최초 생성
    else:

        vector_store = create_vector_store(
            embeddings=embeddings,
        )

    retriever = get_retriever(
        store=vector_store,
        k=10,
    )

    chain = create_rag_chain()

    return (
        vector_store,
        retriever,
        chain,
    )


# =========================================================
# 검색 질문 생성
# =========================================================

def make_search_question(
    question,
    messages,
):

    chat_history = format_chat_history(
        messages
    )

    if chat_history.strip():

        search_question = rewrite_query(
            question=question,
            chat_history=chat_history,
        )

    else:

        search_question = question

    return search_question


# =========================================================
# Document 검색
# =========================================================

def retrieve_documents(
    search_question,
    retriever,
    vector_store,
):

    documents = retriever.invoke(
        search_question
    )

    documents = expand_related_appendices(
        store=vector_store,
        documents=documents,
    )

    return documents


# =========================================================
# 답변 생성
# =========================================================

def generate_answer(
    question,
    messages,
    vector_store,
    retriever,
    chain,
):

    search_question = make_search_question(
        question=question,
        messages=messages,
    )

    documents = retrieve_documents(
        search_question=search_question,
        retriever=retriever,
        vector_store=vector_store,
    )

    context = build_context(
        documents
    )

    response = chain.invoke(
        {
            "question": question,
            "context": context,
        }
    )

    answer = response.get(
        "answer",
        "답변을 생성하지 못했습니다.",
    )

    used_chunk_ids = response.get(
        "used_chunk_ids",
        [],
    )

    raw_followups = response.get(
        "followup_questions",
        [],
    )

    followup_questions = []

    if isinstance(raw_followups, list):

        normalized_question = question.strip()

        for followup in raw_followups:

            if not isinstance(followup, str):
                continue

            followup = followup.strip()

            if (
                not followup
                or followup == normalized_question
                or followup in followup_questions
            ):
                continue

            followup_questions.append(followup)

            if len(followup_questions) == 2:
                break

    sources = build_sources(
        documents=documents,
        used_chunk_ids=used_chunk_ids,
    )

    return {
        "answer": answer,
        "sources": sources,
        "used_chunk_ids": used_chunk_ids,
        "documents": documents,
        "search_question": search_question,
        "followup_questions": followup_questions,
    }
