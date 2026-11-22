"""T260040 real-LLM end-to-end evaluation against a running, isolated API.

Drives the public HTTP API only: register/login -> workspace -> upload -> wait for real
ingestion -> /rag/ask and /rag/ask/stream with the configured *real* LLM. Scores every
answer against the independently labeled ``eval_set.json``.

Retrieval quality and answer quality are reported separately:
- retrieval: is the gold evidence present in the retrieved sources (independent of the LLM)?
- generation: is the answer correct, are its citations grounded in the cited chunk text,
  does it contain numbers that no cited source supports, does it refuse when it should?

A syntactically valid ``[Source N]`` is never counted as grounding by itself.

Usage: python run_real_llm_eval.py --base-url http://127.0.0.1:8765/api/v1 --out report.json
       [--modes stream,ask] [--questions q01,q02]
"""

import argparse
import json
import re
import statistics
import time
import unicodedata
import uuid
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REFUSAL = "Không đủ thông tin trong tài liệu để trả lời câu hỏi này."
UNVERIFIED = "Không thể xác minh câu trả lời từ tài liệu được truy xuất."
CITATION_RE = re.compile(r"\[Source (\d+)\]")
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


def norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


def numbers(text: str) -> set[str]:
    return {n.replace(".", "").replace(",", "") for n in NUMBER_RE.findall(CITATION_RE.sub(" ", text))}


def sse_events(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def score_answer(question: dict, answer: str, sources: list[dict]) -> dict:
    """Score one generated answer against gold labels and the evidence it cites."""
    by_index = {s["source_index"]: s for s in sources}
    cited = sorted({int(n) for n in CITATION_RE.findall(answer)})
    cited_content = " ".join(by_index[i]["content"] for i in cited if i in by_index)
    stripped = answer.strip()
    outcome = "refusal" if stripped == REFUSAL else "unverified" if stripped == UNVERIFIED else "answer"

    result: dict = {"outcome": outcome, "cited": cited}
    if outcome != "answer":
        result.update(correct=not question["answerable"] and outcome == "refusal",
                      grounded=None, unsupported_numbers=[])
        return result

    facts_ok = all(norm(f) in norm(answer) for f in question["required_facts"])
    evidence_cited = bool(question["evidence"]) and norm(question["evidence"]) in norm(cited_content)
    facts_in_cited = all(norm(f) in norm(cited_content) for f in question["required_facts"])
    unsupported = sorted(numbers(answer) - numbers(cited_content))
    result.update(
        correct=question["answerable"] and facts_ok,
        citation_indices_valid=all(i in by_index for i in cited) and bool(cited),
        evidence_in_cited_source=evidence_cited,
        facts_in_cited_source=facts_in_cited if question["answerable"] else False,
        grounded=bool(cited) and facts_in_cited and not unsupported,
        unsupported_numbers=unsupported,
    )
    return result


def retrieval_hit(question: dict, sources: list[dict]) -> bool | None:
    if not question["answerable"]:
        return None
    return any(norm(question["evidence"]) in norm(s["content"]) for s in sources)


class Client:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.http = httpx.Client(base_url=base_url, timeout=timeout)

    def user(self, tag: str) -> str:
        email = f"t260040-{tag}-{uuid.uuid4().hex[:8]}@example.com"
        password = "Str0ng-Passw0rd!"
        assert self.http.post("/auth/register", json={"email": email, "password": password}).status_code == 201
        return self.http.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]

    @staticmethod
    def h(token: str, ws: str | None = None) -> dict:
        headers = {"Authorization": f"Bearer {token}"}
        if ws:
            headers["X-Workspace-Id"] = ws
        return headers

    def ask(self, token: str, ws: str, query: str, conversation_id: str | None = None) -> dict:
        t0 = time.perf_counter()
        r = self.http.post("/rag/ask", headers=self.h(token, ws),
                           json={"query": query, "conversation_id": conversation_id})
        total = time.perf_counter() - t0
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return {"status": r.status_code, "total_s": round(total, 2), "answer": body.get("answer"),
                "sources": body.get("sources", []), "conversation_id": body.get("conversation_id"),
                "model_name": body.get("model_name"), "detail": body.get("detail")}

    def stream(self, token: str, ws: str, query: str, conversation_id: str | None = None) -> dict:
        t0 = time.perf_counter()
        ttft = None
        events: list[dict] = []
        with self.http.stream("POST", "/rag/ask/stream", headers=self.h(token, ws),
                              json={"query": query, "conversation_id": conversation_id}) as r:
            status = r.status_code
            for line in r.iter_lines():
                if line.startswith("data: "):
                    ev = json.loads(line[6:])
                    if ev["event"] == "token" and ttft is None:
                        ttft = time.perf_counter() - t0
                    events.append(ev)
        total = time.perf_counter() - t0
        names = [e["event"] for e in events]
        done = next((e for e in events if e["event"] == "answer_completed"), {})
        retrieved = next((e for e in events if e["event"] == "retrieval_completed"), {}).get("sources", [])
        error = next((e for e in events if e["event"] == "error"), None)
        return {"status": status, "ttft_s": round(ttft, 2) if ttft else None, "total_s": round(total, 2),
                "events": [n for i, n in enumerate(names) if n != "token" or names[i - 1] != "token"],
                "answer": done.get("answer"), "sources": done.get("sources", []), "retrieved": retrieved,
                "conversation_id": done.get("conversation_id"), "message_id": done.get("message_id"),
                "model_name": done.get("model_name"), "error": error,
                # Raw streamed model output, before the server's citation guardrail replaced it.
                "raw_answer": "".join(e["token"] for e in events if e["event"] == "token")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8765/api/v1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--modes", default="stream,ask")
    ap.add_argument("--questions", default="")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--skip-security", action="store_true")
    args = ap.parse_args()

    spec = json.loads((HERE / "eval_set.json").read_text())
    questions = [q for q in spec["questions"] if not args.questions or q["id"] in args.questions.split(",")]
    modes = args.modes.split(",")
    c = Client(args.base_url, args.timeout)
    report: dict = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "modes": modes, "results": [], "checks": {}}

    # --- Journey: auth -> workspace -> upload -> real ingestion
    token_a, token_b = c.user("owner"), c.user("outsider")
    ws_a = c.http.post("/workspaces", headers=c.h(token_a), json={"name": "T260040 eval"}).json()["id"]
    ws_b = c.http.post("/workspaces", headers=c.h(token_b), json={"name": "T260040 outsider"}).json()["id"]
    docs = {}
    t0 = time.perf_counter()
    for name in spec["documents"]:
        r = c.http.post("/documents/upload", headers=c.h(token_a, ws_a),
                        files={"file": (name, (HERE / name).read_bytes(), "text/markdown")})
        assert r.status_code == 201, r.text
        docs[name] = r.json()["id"]
    statuses = {}
    for _ in range(180):
        statuses = {n: c.http.get(f"/documents/{d}", headers=c.h(token_a, ws_a)).json()["status"] for n, d in docs.items()}
        if all(s in ("ready", "failed") for s in statuses.values()):
            break
        time.sleep(1)
    report["checks"]["ingestion"] = {"statuses": statuses, "seconds": round(time.perf_counter() - t0, 1),
                                     "chunks": {n: len(c.http.get(f"/documents/{d}/chunks", headers=c.h(token_a, ws_a)).json()) for n, d in docs.items()}}
    assert all(s == "ready" for s in statuses.values()), statuses

    # --- Labeled questions
    for q in questions:
        for mode in modes:
            res = c.stream(token_a, ws_a, q["question"]) if mode == "stream" else c.ask(token_a, ws_a, q["question"])
            retrieved = res.get("retrieved") or res["sources"]
            row = {"id": q["id"], "mode": mode, "answerable": q["answerable"], **{k: v for k, v in res.items() if k != "retrieved"}}
            row["retrieval_hit"] = retrieval_hit(q, retrieved) if mode == "stream" else None
            if res["answer"] is not None:
                row["score"] = score_answer(q, res["answer"], res["sources"])
            report["results"].append(row)
            print(json.dumps({k: row.get(k) for k in ("id", "mode", "status", "ttft_s", "total_s", "model_name", "answer", "retrieval_hit", "score")}, ensure_ascii=False), flush=True)

    # --- Conversation persistence + follow-up using history
    if "stream" in modes and not args.skip_security:
        first = c.stream(token_a, ws_a, "Thời gian thử việc cho vị trí quản lý ở Lumora là bao lâu?")
        follow = c.stream(token_a, ws_a, "Còn đối với vị trí chuyên viên thì thời gian thử việc là bao lâu?", first["conversation_id"])
        conv = c.http.get(f"/conversations/{first['conversation_id']}", headers=c.h(token_a, ws_a)).json()
        report["checks"]["conversation"] = {
            "first_answer": first["answer"], "follow_up_answer": follow["answer"],
            "follow_up_ttft_s": follow["ttft_s"], "follow_up_total_s": follow["total_s"],
            "follow_up_correct": bool(follow["answer"]) and "45" in follow["answer"],
            "follow_up_score": score_answer({"answerable": True, "required_facts": ["45"], "evidence": "45 ngày đối với vị trí chuyên viên"}, follow["answer"] or "", follow["sources"]),
            "persisted_roles": [m["role"] for m in conv.get("messages", [])],
            "last_message_matches": bool(conv.get("messages")) and conv["messages"][-1]["id"] == follow["message_id"],
        }
        print(json.dumps(report["checks"]["conversation"], ensure_ascii=False), flush=True)

    # --- Cross-workspace isolation with the real LLM in the loop
    if not args.skip_security:
        q1 = spec["questions"][0]["question"]
        forged = c.http.post("/rag/ask", headers=c.h(token_b, ws_a), json={"query": q1})
        own = c.stream(token_b, ws_b, q1)
        a_doc_ids = set(docs.values())
        report["checks"]["isolation"] = {
            "outsider_forged_workspace_status": forged.status_code,
            "outsider_own_workspace_answer": own["answer"],
            "outsider_retrieved_foreign_sources": [s["document_id"] for s in own["retrieved"] if s["document_id"] in a_doc_ids],
            "outsider_read_foreign_doc_status": c.http.get(f"/documents/{docs[spec['documents'][0]]}", headers=c.h(token_b, ws_b)).status_code,
        }
        print(json.dumps(report["checks"]["isolation"], ensure_ascii=False), flush=True)

    report["summary"] = summarize(report["results"])
    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


def summarize(rows: list[dict]) -> dict:
    out = {}
    for mode in sorted({r["mode"] for r in rows}):
        rs = [r for r in rows if r["mode"] == mode]
        ok = [r for r in rs if r["status"] == 200 and r.get("answer") is not None]
        ans = [r for r in ok if r["answerable"]]
        unans = [r for r in ok if not r["answerable"]]
        answered = [r for r in ans if r["score"]["outcome"] == "answer"]
        lat = [r["total_s"] for r in ok]
        ttft = [r["ttft_s"] for r in ok if r.get("ttft_s")]
        out[mode] = {
            "requests": len(rs),
            "errors_or_timeouts": len(rs) - len(ok),
            "answerable_correct": f"{sum(r['score']['correct'] for r in ans)}/{sum(1 for r in rs if r['answerable'])}",
            "answerable_answered": len(answered),
            "answerable_refused_or_unverified": len(ans) - len(answered),
            "answered_grounded": f"{sum(bool(r['score']['grounded']) for r in answered)}/{len(answered)}",
            "answered_with_unsupported_numbers": sum(bool(r["score"]["unsupported_numbers"]) for r in answered),
            "unanswerable_correct_refusal": f"{sum(r['score']['correct'] for r in unans)}/{sum(1 for r in rs if not r['answerable'])}",
            "unanswerable_hallucinated": sum(r["score"]["outcome"] == "answer" for r in unans),
            "retrieval_hit": (f"{sum(bool(r['retrieval_hit']) for r in rs if r['answerable'])}/{sum(1 for r in rs if r['answerable'])}"
                              if mode == "stream" else None),
            "latency_s": {"p50": round(statistics.median(lat), 1), "max": round(max(lat), 1)} if lat else None,
            "ttft_s": {"p50": round(statistics.median(ttft), 1), "max": round(max(ttft), 1)} if ttft else None,
        }
    return out


if __name__ == "__main__":
    main()
