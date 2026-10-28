from datetime import datetime, timedelta, UTC
import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Employee, PointTransaction, Task, TaskCompletion, Reward, Redemption, GuestReview, CleaningMark, Notification, GuestBonus
from .locations import normalize_location


async def register_employee(db: AsyncSession, telegram_id: int, full_name: str, department: str = 'Общий') -> Employee | None:
    existing = await db.scalar(select(Employee).where(Employee.telegram_id == telegram_id))
    if existing:
        return None
    employee = Employee(telegram_id=telegram_id, full_name=full_name.strip(), department=department.strip())
    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    return employee


async def complete_task(db: AsyncSession, employee_id: int, task_id: int):
    task = await db.get(Task, task_id)
    employee = await db.get(Employee, employee_id)
    if not task or not task.active or not employee:
        return False, 'Задание недоступно'
    key = f'task:{employee_id}:{task_id}'
    existing = await db.scalar(select(PointTransaction).where(PointTransaction.idempotency_key == key))
    if existing:
        return True, 'Награда за это задание уже получена'
    db.add(TaskCompletion(employee_id=employee_id, task_id=task_id))
    employee.points += task.points
    db.add(PointTransaction(employee_id=employee_id, amount=task.points, reason=f'Задание: {task.title}', idempotency_key=key))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return True, 'Награда уже получена'
    return True, f'Задание выполнено! Начислено {task.points} баллов'


async def redeem_reward(db: AsyncSession, employee_id: int, reward_id: int, request_key: str = '') -> tuple[bool, str]:
    employee = await db.get(Employee, employee_id)
    reward = await db.get(Reward, reward_id)
    if not employee or not reward or not reward.active:
        return False, 'Награда недоступна'
    key = request_key.strip() or f'redeem:{employee_id}:{reward_id}'
    previous = await db.scalar(select(Redemption).where(Redemption.idempotency_key == key))
    if previous:
        return True, 'Запрос уже обработан'
    if employee.points < reward.cost:
        return False, 'Недостаточно баллов'
    if reward.stock < 1:
        return False, 'Награды закончились'
    employee.points -= reward.cost
    reward.stock -= 1
    db.add(Redemption(employee_id=employee_id, reward_id=reward_id, idempotency_key=key, status='pending'))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return True, 'Запрос уже обработан'
    return True, 'Награда успешно получена!'


GUEST_BONUSES = (
    ('🍫 Шоколад Swissôtel', 'Бесплатная шоколадка при предъявлении промокода на стойке guest relations.'),
    ('🍽️ Скидка 10% в ресторане', 'Скидка 10% на счёт ресторана отеля при предъявлении промокода.'),
    ('🛍️ Скидка 10% в бутике', 'Скидка 10% в магазине отеля при наличии действующего промокода.'),
    ('💆 Скидка 15% в SPA', 'Скидка 15% на одну spa-услугу по согласованию с SPA-центром.'),
    ('☕ Напиток отеля', 'Один бесплатный кофе или чай в кофейне отеля.'),
    ('🥐 Завтрак-визитка', 'Скидка 15% на завтрак на один визит в ресторане отеля.'),
)


async def assign_guest_bonus(db: AsyncSession, review: GuestReview) -> GuestBonus | None:
    existing = await db.scalar(select(GuestBonus).where(GuestBonus.review_id == review.id))
    if existing:
        return existing
    title, description = secrets.choice(GUEST_BONUSES)
    while True:
        code = 'SW-' + secrets.token_hex(4).upper()
        if not await db.scalar(select(GuestBonus).where(GuestBonus.code == code)):
            break
    bonus = GuestBonus(
        review_id=review.id,
        title=title,
        description=description,
        code=code,
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=31),
    )
    db.add(bonus)
    await db.flush()
    return bonus


async def register_guest_review(db: AsyncSession, review: GuestReview) -> int | None:
    review.room_number = normalize_location(review.room_number)
    location = review.room_number.casefold()
    marks = (await db.scalars(select(CleaningMark).order_by(CleaningMark.created_at.desc()))).all()
    marks = [mark for mark in marks if normalize_location(mark.location).casefold() == location]
    employee = await db.get(Employee, marks[0].employee_id) if marks else None
    if employee:
        review.employee_id = employee.id

    db.add(review)
    await db.flush()
    await assign_guest_bonus(db, review)

    if employee:
        key = f'review-quality:{review.id}'
        if not await db.scalar(select(PointTransaction).where(PointTransaction.idempotency_key == key)):
            amount = review.rating * 10
            employee.points += amount
            db.add(PointTransaction(employee_id=employee.id, amount=amount, reason=f'{review.rating} звёзд за уборку {review.room_number}', idempotency_key=key))

    if employee:
        db.add(Notification(
            employee_id=employee.id,
            text=(f'💬 Новый отзыв: «{review.room_number}», оценка {review.rating}/5.\n'
                  f'{review.comment[:500]}'),
        ))
    await db.commit()
    await db.refresh(review)
    return employee.id if employee else None


async def backfill_review_links(db: AsyncSession) -> int:
    marks = (await db.scalars(select(CleaningMark).order_by(CleaningMark.created_at))).all()
    reviews = (await db.scalars(select(GuestReview).order_by(GuestReview.created_at))).all()
    linked = 0
    for review in reviews:
        await assign_guest_bonus(db, review)
        location = normalize_location(review.room_number).casefold()
        applicable = [
            mark for mark in marks
            if normalize_location(mark.location).casefold() == location
            and mark.created_at <= review.created_at
        ]
        if not applicable:
            continue
        employee_id = applicable[-1].employee_id
        changed = review.employee_id != employee_id
        review.employee_id = employee_id
        employee = await db.get(Employee, employee_id)
        key = f'review-quality:{review.id}'
        if employee and not await db.scalar(select(PointTransaction).where(PointTransaction.idempotency_key == key)):
            amount = review.rating * 10
            employee.points += amount
            db.add(PointTransaction(employee_id=employee_id, amount=amount, reason=f'{review.rating} звёзд за уборку {review.room_number}', idempotency_key=key))
        if changed:
            linked += 1
            exists = await db.scalar(
                select(Notification.id).where(
                    Notification.employee_id == employee_id,
                    Notification.text.contains(f'отзыв №{review.id}'),
                )
            )
            if not exists:
                db.add(Notification(
                    employee_id=employee_id,
                    text=(f'💬 отзыв №{review.id}: {normalize_location(review.room_number)}, '
                          f'оценка {review.rating}/5\nКомментарий гостя: {review.comment}'),
                ))
    await db.commit()
    return linked
