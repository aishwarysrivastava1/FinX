# backend/routers/search.py
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from services.search_service import search_stock

router = APIRouter()


@router.get('/search')
def search_stocks(q: str = Query('', max_length=50)):
    """
    Smart NSE stock search with typo correction.
    Returns top 5 matching stocks as [{symbol, name}].
    Example: /api/search?q=relaince  →  RELIANCE
    """
    try:
        results = search_stock(q.strip())
        return {
            'success': True,
            'data': {'results': results},
            'error': None,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={'success': False, 'data': None, 'error': str(e)},
        )
