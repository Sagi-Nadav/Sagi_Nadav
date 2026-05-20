from datetime import datetime, date, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from .database import Task


def _current_week_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def get_week_tasks(db: Session, week_of: Optional[date] = None) -> list[Task]:
    if week_of is None:
        week_of = _current_week_monday()
    return db.query(Task).filter(Task.week_of == week_of).order_by(Task.priority, Task.created_at).all()


def get_today_tasks(db: Session) -> list[Task]:
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())
    return (
        db.query(Task)
        .filter(
            Task.status.in_(["open", "in_progress"]),
            (Task.due_date <= today_end) | (Task.due_date == None),
        )
        .order_by(Task.priority, Task.due_date)
        .all()
    )


def get_incomplete_tasks(db: Session) -> list[Task]:
    return (
        db.query(Task)
        .filter(Task.status.in_(["open", "in_progress"]))
        .order_by(Task.week_of.desc(), Task.priority)
        .all()
    )


def get_weekly_summary(db: Session, week_of: Optional[date] = None) -> dict:
    if week_of is None:
        week_of = _current_week_monday()
    tasks = get_week_tasks(db, week_of)
    summary = {"open": 0, "in_progress": 0, "done": 0, "deferred": 0, "total": len(tasks)}
    for t in tasks:
        summary[t.status] = summary.get(t.status, 0) + 1
    return summary


def create_task(
    db: Session,
    title: str,
    description: Optional[str] = None,
    priority: int = 2,
    due_date: Optional[datetime] = None,
    week_of: Optional[date] = None,
) -> Task:
    if week_of is None:
        week_of = _current_week_monday()
    task = Task(
        title=title,
        description=description,
        status="open",
        priority=priority,
        week_of=week_of,
        due_date=due_date,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, task_id: int, **kwargs) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise ValueError(f"Task {task_id} not found")
    for key, value in kwargs.items():
        if hasattr(task, key):
            setattr(task, key, value)
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task_id: int) -> None:
    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        db.delete(task)
        db.commit()


def complete_task(db: Session, task_id: int) -> Task:
    return update_task(db, task_id, status="done")
