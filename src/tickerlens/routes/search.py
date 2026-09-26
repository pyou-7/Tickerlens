from __future__ import annotations

from fastapi import APIRouter, Query

from tickerlens.services.search import CompanySearchResult, CompanySearchService

router = APIRouter()
_search_service = CompanySearchService()


@router.get("/api/search", response_model=list[CompanySearchResult])
def search_companies(
    q: str = Query("", description="Search term for ticker or company name"),
    limit: int = Query(8, ge=1, le=20, description="Max number of suggestions to return"),
) -> list[CompanySearchResult]:
    """Search company universe by ticker or name and return ranked suggestions."""
    return _search_service.search(query=q, limit=limit)
