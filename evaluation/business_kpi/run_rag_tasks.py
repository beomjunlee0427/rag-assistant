"""Run the saved RAG task questions through the project's chatbot and save answers."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.rag.chatbot import generate_answer, initialize_rag  # noqa: E402


TASKS_PATH = ROOT / "evaluation" / "business_kpi" / "rag_tasks.csv"
OUTPUT_PATH = ROOT / "evaluation" / "results" / "business_kpi_rag_answers.csv"
OUTPUT_FIELDS = [
    "task_id",
    "question",
    "reference_answer",
    "reference_evidence",
    "rag_answer",
    "rag_used_chunk_ids",
    "rag_sources",
    "status",
    "error",
]


def read_tasks() -> list[dict[str, str]]:
    with TASKS_PATH.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_results(rows: list[dict[str, str]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    tasks = read_tasks()
    if not tasks:
        raise RuntimeError(f"평가 질문이 없습니다: {TASKS_PATH}")

    print(f"RAG 초기화 중: {len(tasks)}개 질문")
    vector_store, retriever, chain = initialize_rag()
    results: list[dict[str, str]] = []

    for index, task in enumerate(tasks, start=1):
        task_id = task["task_id"]
        question = task["question"]
        print(f"[{index}/{len(tasks)}] {task_id}: {question}")

        try:
            response = generate_answer(
                question=question,
                messages=[],
                vector_store=vector_store,
                retriever=retriever,
                chain=chain,
            )
            row = {
                "task_id": task_id,
                "question": question,
                "reference_answer": task.get("reference_answer", ""),
                "reference_evidence": task.get("reference_evidence", ""),
                "rag_answer": response.get("answer", ""),
                "rag_used_chunk_ids": "|".join(response.get("used_chunk_ids", [])),
                "rag_sources": "|".join(response.get("sources", [])),
                "status": "success",
                "error": "",
            }
            print(f"    답변: {row['rag_answer'][:160]}")
            print(f"    근거: {row['rag_used_chunk_ids'] or '(응답에서 근거 ID 없음)'}")
        except Exception as exc:  # Keep later questions running if one request fails.
            row = {
                "task_id": task_id,
                "question": question,
                "reference_answer": task.get("reference_answer", ""),
                "reference_evidence": task.get("reference_evidence", ""),
                "rag_answer": "",
                "rag_used_chunk_ids": "",
                "rag_sources": "",
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"    오류: {row['error']}")

        results.append(row)
        write_results(results)

    succeeded = sum(row["status"] == "success" for row in results)
    failed = len(results) - succeeded
    print(f"완료: 성공 {succeeded}개, 실패 {failed}개")
    print(f"결과 파일: {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
