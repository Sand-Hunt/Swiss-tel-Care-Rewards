import pytest
from httpx import ASGITransport, AsyncClient
from app.web.app import app
from app.db import get_session, SessionLocal

@pytest.mark.asyncio
async def test_api_review(db, db_engine):
    import app.db as db_module
    original = db_module.SessionLocal
    db_module.SessionLocal = lambda: db
    async def override_session():
        yield db
    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/reviews', json={'guest_name':'Гость','room_number':'101','rating':5,'comment':'Отличное обслуживание!'})
        assert response.status_code == 200
        assert response.json()['status'] == 'accepted'
    app.dependency_overrides.clear()
    db_module.SessionLocal = original

@pytest.mark.asyncio
async def test_review_validation(client=None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/reviews', json={'guest_name':'Гость','rating':6,'comment':'Комментарий'})
        assert response.status_code == 422
        response = await client.post('/api/reviews', json={'guest_name':'Гость','rating':5,'comment':'Хорошее обслуживание'})
        assert response.status_code == 422
