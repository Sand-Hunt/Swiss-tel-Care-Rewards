from datetime import datetime
from enum import Enum
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class EmployeeRole(str, Enum):
    EMPLOYEE = 'employee'
    MANAGER = 'manager'
    ADMIN = 'admin'


class IssueStatus(str, Enum):
    NEW = 'new'
    IN_PROGRESS = 'in_progress'
    DONE = 'done'


class Employee(Base):
    __tablename__ = 'employees'
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    department: Mapped[str] = mapped_column(String(100), default='Общий')
    role: Mapped[str] = mapped_column(String(20), default=EmployeeRole.EMPLOYEE.value)
    points: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class GuestReview(Base):
    __tablename__ = 'guest_reviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    guest_name: Mapped[str] = mapped_column(String(100))
    room_number: Mapped[str] = mapped_column(String(20), nullable=False)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey('employees.id'), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class GuestBonus(Base):
    __tablename__ = 'guest_bonuses'
    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey('guest_reviews.id'), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500))
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CleaningMark(Base):
    __tablename__ = 'cleaning_marks'
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey('employees.id'))
    location: Mapped[str] = mapped_column(String(100), index=True)
    note: Mapped[str] = mapped_column(String(500), default='')
    points: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey('employees.id'), index=True)
    text: Mapped[str] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AdaptationSurvey(Base):
    __tablename__ = 'adaptation_surveys'
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey('employees.id'))
    answers: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EmployeeIssue(Base):
    __tablename__ = 'employee_issues'
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey('employees.id'))
    category: Mapped[str] = mapped_column(String(50))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=IssueStatus.NEW.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    points: Mapped[int] = mapped_column(Integer, default=10)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TaskCompletion(Base):
    __tablename__ = 'task_completions'
    __table_args__ = (UniqueConstraint('employee_id', 'task_id', name='uq_employee_task'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey('employees.id'))
    task_id: Mapped[int] = mapped_column(ForeignKey('tasks.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PointTransaction(Base):
    __tablename__ = 'point_transactions'
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey('employees.id'))
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200))
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Reward(Base):
    __tablename__ = 'rewards'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    cost: Mapped[int] = mapped_column(Integer)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Redemption(Base):
    __tablename__ = 'redemptions'
    __table_args__ = (UniqueConstraint('employee_id', 'reward_id', 'idempotency_key', name='uq_redemption_key'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey('employees.id'))
    reward_id: Mapped[int] = mapped_column(ForeignKey('rewards.id'))
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default='pending', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
