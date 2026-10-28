from pathlib import Path
from fastapi import FastAPI, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import init_db, get_session, SessionLocal
from ..models import GuestReview, CleaningMark, Employee, GuestBonus
from ..locations import normalize_location
from ..schemas import ReviewCreate
from ..seed import seed_demo_data
from ..services import register_guest_review, backfill_review_links

app = FastAPI(title='Swissôtel Care & Rewards')
templates = Jinja2Templates(directory=Path(__file__).parent / 'templates')

@app.on_event('startup')
async def startup():
    await init_db()
    await seed_demo_data()
    async with SessionLocal() as db:
        await backfill_review_links(db)

@app.get('/reviews', response_class=HTMLResponse)
async def review_form(request: Request):
    return templates.TemplateResponse('review.html', {'request': request, 'success': False})

@app.post('/reviews', response_class=HTMLResponse)
async def submit_review(request: Request, guest_name: str = Form(...), room_number: str = Form(...), rating: int = Form(..., ge=1, le=5), comment: str = Form(...), db: AsyncSession = Depends(get_session)):
    if len(comment.strip()) < 5 or len(guest_name.strip()) < 1 or len(room_number.strip()) < 1:
        return templates.TemplateResponse('review.html', {'request': request, 'success': False, 'guest_name': guest_name, 'room_number': room_number, 'comment': comment, 'error': True}, status_code=400)
    payload = ReviewCreate(guest_name=guest_name.strip(), room_number=room_number.strip(), rating=rating, comment=comment.strip())
    review = GuestReview(**payload.model_dump())
    await register_guest_review(db, review)
    bonus = await db.scalar(select(GuestBonus).where(GuestBonus.review_id == review.id))
    return templates.TemplateResponse('review.html', {
        'request': request,
        'success': True,
        'submitted_at': review.created_at.strftime('%d.%m.%Y %H:%M'),
        'bonus_title': bonus.title,
        'bonus_description': bonus.description,
        'bonus_code': bonus.code,
        'bonus_expires_at': bonus.expires_at.strftime('%d.%m.%Y'),
    })

@app.get('/cleaning-history', response_class=HTMLResponse)
async def cleaning_history(request: Request, db: AsyncSession = Depends(get_session)):
    marks = (await db.scalars(select(CleaningMark).order_by(CleaningMark.created_at.desc()).limit(500))).all()
    reviews = (await db.scalars(select(GuestReview).order_by(GuestReview.created_at.desc()).limit(500))).all()
    employees = (await db.scalars(select(Employee))).all()
    employee_names = {employee.id: employee.full_name for employee in employees}

    history = []
    for mark in marks:
        normalized = normalize_location(mark.location).casefold()
        newer_marks = [other for other in marks if normalize_location(other.location).casefold() == normalized and other.created_at > mark.created_at]
        upper_bound = min((other.created_at for other in newer_marks), default=None)
        location_reviews = []
        for review in reviews:
            if normalize_location(review.room_number).casefold() != normalized:
                continue
            if review.created_at < mark.created_at:
                continue
            if upper_bound and review.created_at >= upper_bound:
                continue
            location_reviews.append(review)
        mark_data = {
            'location': normalize_location(mark.location),
            'note': mark.note,
            'created_at': mark.created_at,
            'employee_name': employee_names.get(mark.employee_id, 'Сотрудник не найден'),
            'reviews': location_reviews,
        }
        history.append(mark_data)

    return templates.TemplateResponse('cleaning_history.html', {'request': request, 'marks': history})


@app.post('/api/reviews', response_model=None)
async def api_review(payload: ReviewCreate, db: AsyncSession = Depends(get_session)):
    review = GuestReview(**payload.model_dump())
    await register_guest_review(db, review)
    bonus = await db.scalar(select(GuestBonus).where(GuestBonus.review_id == review.id))
    return {
        'id': review.id,
        'status': 'accepted',
        'bonus': {
            'title': bonus.title,
            'description': bonus.description,
            'code': bonus.code,
            'expires_at': bonus.expires_at.isoformat(),
        },
    }

@app.get('/api/reviews')
async def list_reviews(db: AsyncSession = Depends(get_session)):
    reviews = (await db.scalars(select(GuestReview).order_by(GuestReview.id.desc()).limit(100))).all()
    return [{'id': r.id, 'guest_name': r.guest_name, 'room_number': r.room_number, 'rating': r.rating, 'comment': r.comment} for r in reviews]
