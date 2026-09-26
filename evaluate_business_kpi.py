"""Calculate business-facing KPIs from the editable evaluation CSV templates."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parent
BASE = ROOT / "evaluation" / "business_kpi"
RESULTS = ROOT / "evaluation" / "results"


def read_csv(name: str) -> list[dict[str, str]]:
    path = BASE / name
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"숫자 입력이 필요합니다: {value!r}") from exc
    if result < 0:
        raise ValueError(f"시간/건수는 음수일 수 없습니다: {value!r}")
    return result


def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def average(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return mean(present) if present else None


def time_metrics(rows: list[dict[str, str]]) -> dict[str, float | None]:
    manual = [number(row.get("manual_time_sec")) for row in rows]
    ai = [number(row.get("ai_time_sec")) for row in rows]
    manual_avg, ai_avg = average(manual), average(ai)
    reduction = (
        (manual_avg - ai_avg) / manual_avg
        if manual_avg is not None and ai_avg is not None and manual_avg > 0
        else None
    )
    return {
        "manual_avg_time_sec": manual_avg,
        "ai_avg_time_sec": ai_avg,
        "time_reduction_rate": reduction,
        "time_pairs_available": sum(m is not None and a is not None for m, a in zip(manual, ai)),
        "time_data_note": "manual time is simulated; AI time is from a prior saved experiment, not the current live run",
    }


def count_choice(rows: list[dict[str, str]], field: str, choice: str) -> int:
    return sum(row.get(field, "").strip().lower() == choice for row in rows)


def rag_metrics() -> dict[str, object]:
    tasks = read_csv("rag_tasks.csv")
    reviews = read_csv("rag_review.csv")
    times = read_csv("rag_time_log.csv")
    evaluated = [row for row in reviews if row.get("answer_correctness", "").strip()]
    evidence_evaluated = [row for row in reviews if row.get("evidence_valid", "").strip()]
    rework_evaluated = [row for row in reviews if row.get("rework_level", "").strip()]
    return {
        "task_count": len(tasks),
        **time_metrics(times),
        "evaluation_data_note": "ratings are provisional AI review of current live answers and cited evidence; human confirmation is pending",
        "answer_correctness_rate": ratio(count_choice(evaluated, "answer_correctness", "correct"), len(evaluated)),
        "answer_reviews_completed": len(evaluated),
        "evidence_validity_rate": ratio(count_choice(evidence_evaluated, "evidence_valid", "yes"), len(evidence_evaluated)),
        "evidence_reviews_completed": len(evidence_evaluated),
        "rework_rate": ratio(sum(row.get("rework_level", "").strip().lower() in {"minor", "major"} for row in rework_evaluated), len(rework_evaluated)),
        "rework_reviews_completed": len(rework_evaluated),
    }


def make_rag_task_set() -> None:
    """Refresh the RAG tasks and empty input templates from the existing Golden Set."""
    source = ROOT / "evaluation" / "golden_set.csv"
    with source.open(encoding="utf-8-sig", newline="") as file:
        golden_rows = list(csv.DictReader(file))
    if len(golden_rows) < 20:
        raise ValueError(f"Golden Set에 질문이 20개 미만입니다: {len(golden_rows)}")
    selected = golden_rows[:25]
    tasks = []
    for index, row in enumerate(selected, start=1):
        tasks.append({
            "task_id": f"RAG_{index:03d}",
            "source_query_id": row["query_id"],
            "question": row["query"],
            "reference_answer": row["gold_answer"],
            "reference_evidence": row["gold_chunks"],
        })
    BASE.mkdir(parents=True, exist_ok=True)
    write_csv(BASE / "rag_tasks.csv", tasks)
    write_csv(BASE / "rag_time_log.csv", [
        {"task_id": row["task_id"], "question": row["question"], "manual_time_sec": "", "ai_time_sec": ""}
        for row in tasks
    ])
    write_csv(BASE / "rag_review.csv", [
        {"task_id": row["task_id"], "question": row["question"], "answer_correctness": "", "evidence_valid": "", "rework_level": "", "reviewer_note": ""}
        for row in tasks
    ])


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def pct(value: object) -> str:
    return "미측정" if value is None else f"{value:.1%}"


def seconds(value: object) -> str:
    return "미측정" if value is None else f"{value:.1f}초"


def report(data: dict[str, object]) -> str:
    rag = data["rag"]
    return f"""# Business KPI 예비 평가 결과

> 현재 RAG 답변은 실제 실행 결과입니다. 답변·근거·재작업 평가는 AI 예비 검토이며 사람의 확인이 필요합니다. 수작업 시간은 시나리오 시뮬레이션 값이고, AI 시간은 이전 저장 실험의 기록값입니다.

## 1차 RAG

| KPI | 결과 | 대상 건수 |
|---|---:|---:|
| 평균 수작업 탐색시간 | {seconds(rag['manual_avg_time_sec'])} | {rag['time_pairs_available']} |
| 평균 AI 탐색시간 | {seconds(rag['ai_avg_time_sec'])} | {rag['time_pairs_available']} |
| 탐색시간 단축률 | {pct(rag['time_reduction_rate'])} | {rag['time_pairs_available']} |
| 업무 질의 정확 처리율 | {pct(rag['answer_correctness_rate'])} | {rag['answer_reviews_completed']} |
| 근거 확인 가능률 | {pct(rag['evidence_validity_rate'])} | {rag['evidence_reviews_completed']} |
| 재작업률 | {pct(rag['rework_rate'])} | {rag['rework_reviews_completed']} |

## 계산 기준

- 시간 단축률 = (평균 수작업 시간 - 평균 AI 시간) / 평균 수작업 시간
- 정확 처리율 = `correct` 평가 건수 / 해당 항목 평가 완료 건수
- 근거 확인 가능률 = `yes` / evidence 평가 완료 건수
- 재작업률 = (`minor` + `major`) / rework 평가 완료 건수
이 보고서의 시간 단축률은 수작업 시나리오 시간과 이전 AI 실행 시간을 비교한 참고값입니다. 답변·근거·재작업 KPI는 실제 RAG 답변에 대한 AI 예비 판정이므로 사람 검토 후 확정해야 합니다. Hit@K, Precision@K, MRR 등 기술 검색 KPI는 이 Business KPI에 포함하지 않습니다.
"""


def write_summary(data: dict[str, object]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "business_kpi_summary.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    flat = []
    for metric, value in data["rag"].items():
        flat.append({"project": "rag", "metric": metric, "value": "" if value is None else value})
    with (RESULTS / "business_kpi_summary.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["project", "metric", "value"])
        writer.writeheader()
        writer.writerows(flat)
    (RESULTS / "business_kpi_report.md").write_text(report(data), encoding="utf-8")


def main() -> None:
    data = {"rag": rag_metrics()}
    data["data_status"] = {
        "status": "live_answers_with_provisional_ai_review_and_simulated_manual_times",
        "manual_time_sec": "simulated scenario values; not observed",
        "ai_time_sec": "prior saved experiment values; current live answer run was not timed",
        "human_review": "AI provisional labels; human confirmation pending",
    }
    write_summary(data)
    print(report(data))
    print(f"\n결과 저장 위치: {RESULTS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
