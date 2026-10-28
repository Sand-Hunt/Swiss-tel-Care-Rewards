import pytest
from app.models import Employee, Task, Reward, CleaningMark, GuestReview, GuestBonus
from sqlalchemy import select
from app.services import complete_task, redeem_reward, register_guest_review

@pytest.mark.asyncio
async def test_task_award_is_idempotent(db):
    employee = Employee(telegram_id=1, full_name='Тест Сотрудник', points=0)
    task = Task(title='Тестовое задание', description='Описание', points=25)
    db.add_all([employee, task]); await db.flush()
    employee_id, task_id = employee.id, task.id
    ok, _ = await complete_task(db, employee_id, task_id)
    await db.refresh(employee)
    assert ok and employee.points == 25
    ok, _ = await complete_task(db, employee_id, task_id)
    await db.refresh(employee)
    assert ok and employee.points == 25

@pytest.mark.asyncio
async def test_redemption_is_idempotent(db):
    employee = Employee(telegram_id=2, full_name='Тест Сотрудник 2', points=100)
    reward = Reward(name='Кружка', description='Подарок', cost=40, stock=2)
    db.add_all([employee, reward]); await db.flush()
    ok, _ = await redeem_reward(db, employee.id, reward.id, 'test-redemption-1')
    await db.refresh(employee)
    assert ok and employee.points == 60
    ok, _ = await redeem_reward(db, employee.id, reward.id, 'test-redemption-1')
    await db.refresh(employee)
    assert ok and employee.points == 60

@pytest.mark.asyncio
async def test_registration_and_redeem_validation(db):
    employee = Employee(telegram_id=3, full_name='Тест', points=0)
    reward = Reward(name='Бесплатно', description='Тест', cost=40, stock=1)
    db.add_all([employee, reward]); await db.commit()
    ok, message = await redeem_reward(db, employee.id, reward.id)
    assert not ok
    assert 'Недостаточно' in message


@pytest.mark.asyncio
async def test_review_is_assigned_and_quality_points_awarded(db):
    employee = Employee(telegram_id=4, full_name='Горничная Тест', points=0)
    db.add(employee)
    await db.flush()
    db.add(CleaningMark(employee_id=employee.id, location='Номер 12'))
    await db.commit()
    review = GuestReview(guest_name='Гость', room_number='Номер 12', rating=5, comment='Очень чисто и аккуратно')
    assigned_id = await register_guest_review(db, review)
    await db.refresh(employee)
    assert assigned_id == employee.id
    assert employee.points == 50
    assert review.employee_id == employee.id
    bonus = await db.scalar(select(GuestBonus).where(GuestBonus.review_id == review.id))
    assert bonus is not None
    assert bonus.code.startswith('SW-')


@pytest.mark.asyncio
async def test_numeric_room_matches_normalized_mark(db):
    employee = Employee(telegram_id=5, full_name='Горничная Номер 111', points=0)
    db.add(employee)
    await db.flush()
    db.add(CleaningMark(employee_id=employee.id, location='номер 111'))
    await db.commit()
    review = GuestReview(guest_name='Гость', room_number='111', rating=5, comment='Уборка выполнена отлично')
    assigned_id = await register_guest_review(db, review)
    assert assigned_id == employee.id
    assert review.room_number == 'Номер 111'
