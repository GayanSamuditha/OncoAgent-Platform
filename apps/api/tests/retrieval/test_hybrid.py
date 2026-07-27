from app.retrieval.reranking import DeterministicFakeReranker
from app.retrieval.search import reciprocal_rank_fusion


def item(document_id: str, score: float) -> dict[str, object]:
    return {"document_id": document_id, "similarity_score": score, "text_excerpt": document_id}


def test_rrf_preserves_branch_ranks_and_is_deterministic() -> None:
    lexical = [item("a", 1.0), item("b", 0.5)]
    dense = [item("b", 0.9), item("a", 0.8)]
    first = reciprocal_rank_fusion(lexical, dense, constant=60, limit=2)
    second = reciprocal_rank_fusion(lexical, dense, constant=60, limit=2)
    assert first == second
    assert first[0]["lexical_rank"] == 1
    assert first[0]["dense_rank"] == 2
    assert first[1]["dense_rank"] == 1
    assert first[1]["lexical_rank"] == 2


def test_fake_reranker_orders_term_overlap() -> None:
    reranker = DeterministicFakeReranker()
    candidates = [{"text_excerpt": "blood pressure observation"}, {"text_excerpt": "colonoscopy procedure"}]
    assert reranker.rerank("blood pressure", candidates)[0] > reranker.rerank("blood pressure", candidates)[1]
