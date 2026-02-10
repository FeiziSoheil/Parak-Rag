"""Search and collection info API: categories, collection analysis, enhanced search."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.models.user import User
from app.services.rag import (
    analyze_collection_data,
    enhanced_search_with_llm,
    products_from_search_results,
)

router = APIRouter()


class SearchBody(BaseModel):
    query: str
    price_max: float | None = None
    category: str | None = None
    limit: int = 10


@router.get("/search/categories")
def get_categories(current_user: User = Depends(get_current_user)):
    """Return list of categories and price stats from the Qdrant collection (for filters and enhanced search)."""
    data = analyze_collection_data()
    return {
        "categories": data["categories"],
        "category_count": data["category_count"],
        "price_stats": data["price_stats"],
        "total_products": data["total_products"],
    }


@router.post("/search")
def post_search(
    body: SearchBody,
    current_user: User = Depends(get_current_user),
):
    """Enhanced search: LLM extracts keywords/filters from natural language, then vector search. Returns results and summary."""
    out = enhanced_search_with_llm(
        user_query=body.query,
        limit=body.limit,
        price_max=body.price_max,
        category=body.category,
    )
    products = products_from_search_results(out["results"])
    return {
        "query": out["query"],
        "results": out["results"],
        "products": products,
        "summary": out["summary"],
        "filters_applied": out["filters_applied"],
    }
