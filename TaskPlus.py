import os
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from database import SessionLocal, Task, generate_id, init_db


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(CURRENT_DIR, "static")
VALID_STATUSES = ["pending", "in-progress", "completed"]

app = FastAPI()


@app.on_event("startup")
def startup() -> None:
    init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def validate_due_date(due_date: Optional[str], allow_past: bool = False) -> Optional[str]:
    if not due_date:
        return None

    try:
        parsed_date = datetime.fromisoformat(due_date).date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format") from exc

    if not allow_past and parsed_date < datetime.now().date():
        raise HTTPException(status_code=400, detail="Due date cannot be in the past")

    return parsed_date.isoformat()


def task_to_dict(task: Task) -> dict:
    return {
        "title": task.title,
        "description": task.description or "",
        "status": task.status,
        "due_date": task.due_date,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


@app.post("/tasks")
def create_task(
    title: str,
    description: str = "",
    due_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if not title or not title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    task_id = generate_id()
    task = Task(
        id=task_id,
        title=title.strip(),
        description=description,
        status="pending",
        due_date=validate_due_date(due_date),
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    return {
        "message": "Task created successfully",
        "task_id": task_id,
        "task": task_to_dict(task),
    }


@app.get("/tasks")
def get_all_tasks(db: Session = Depends(get_db)):
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    return {task.id: task_to_dict(task) for task in tasks}


@app.get("/stats")
def get_statistics(db: Session = Depends(get_db)):
    total = db.query(Task).count()

    if total == 0:
        return {
            "total_tasks": 0,
            "pending": 0,
            "completed": 0,
            "completion_rate": "0%",
        }

    completed = db.query(Task).filter(Task.status == "completed").count()
    pending = total - completed
    rate = completed / total * 100

    return {
        "total_tasks": total,
        "pending": pending,
        "completed": completed,
        "completion_rate": f"{rate:.1f}%",
    }


@app.get("/tasks/overdue")
def get_overdue_tasks(db: Session = Depends(get_db)):
    today = datetime.now().date().isoformat()
    tasks = db.query(Task).filter(Task.due_date.is_not(None), Task.status != "completed").all()
    overdue = {task.id: task_to_dict(task) for task in tasks if task.due_date and task.due_date < today}

    if not overdue:
        return {"message": "No overdue tasks", "tasks": {}}

    return {
        "count": len(overdue),
        "tasks": overdue,
    }


@app.get("/tasks/by-date-range")
def get_tasks_by_date_range(start_date: str, end_date: str, db: Session = Depends(get_db)):
    try:
        start = datetime.fromisoformat(start_date).date()
        end = datetime.fromisoformat(end_date).date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format") from exc

    tasks = db.query(Task).filter(Task.due_date.is_not(None)).all()
    matching = {}
    for task in tasks:
        due = datetime.fromisoformat(task.due_date).date()
        if start <= due <= end:
            matching[task.id] = task_to_dict(task)

    return {
        "date_range": f"{start_date} to {end_date}",
        "count": len(matching),
        "tasks": matching,
    }


@app.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_to_dict(task)


@app.put("/tasks/{task_id}")
def update_task(
    task_id: str,
    title: str,
    description: str,
    status: str,
    due_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if not title or not title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {VALID_STATUSES}")

    task.title = title.strip()
    task.description = description
    task.status = status
    task.due_date = validate_due_date(due_date, allow_past=True)

    db.commit()
    db.refresh(task)

    return {
        "message": "Task updated successfully",
        "task": task_to_dict(task),
    }


@app.patch("/tasks/{task_id}/status")
def update_status(task_id: str, status: str, db: Session = Depends(get_db)):
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = status
    db.commit()
    db.refresh(task)

    return {
        "message": f"Status updated to {status}",
        "task": task_to_dict(task),
    }


@app.post("/tasks/{task_id}/toggle")
def toggle_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = "completed" if task.status != "completed" else "pending"
    db.commit()
    db.refresh(task)

    return {
        "message": f"Task toggled to {task.status}",
        "task": task_to_dict(task),
    }


@app.delete("/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()
    return {"message": "Task deleted successfully"}


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    try:
        html_path = os.path.join(STATIC_DIR, "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Error: index.html not found in static folder</h1>",
            status_code=404,
        )
    except Exception as exc:
        return HTMLResponse(
            content=f"<h1>Error: {str(exc)}</h1>",
            status_code=500,
        )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
