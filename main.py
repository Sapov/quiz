from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeSerializer, BadSignature
import random
import time

from questions import QUESTIONS

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

SECRET = "ertev<JNKdf"
serializer = URLSafeSerializer(SECRET)
COOKIE_NAME = "quiz_state"
QUESTION_TIME_LIMIT = 15  # секунд на вопрос


# ---------- Работа с состоянием в cookie ----------
def get_state(request: Request) -> dict | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        return serializer.loads(raw)
    except BadSignature:
        return None


def set_state(response, state: dict):
    response.set_cookie(
        COOKIE_NAME,
        serializer.dumps(state),
        httponly=True,
        max_age=3600,
        samesite="lax",
    )


# ---------- Старт / рестарт ----------
@app.get("/", response_class=HTMLResponse)
async def start():
    order = list(range(len(QUESTIONS)))
    random.shuffle(order)
    state = {
        "order": order,
        "current": 0,
        "score": 0,
        "answers": [],  # какие ответы дал пользователь
    }
    response = RedirectResponse(url="/question", status_code=303)
    set_state(response, state)
    return response


# ---------- Показ вопроса ----------
@app.get("/question", response_class=HTMLResponse)
async def show_question(request: Request):
    state = get_state(request)
    if not state:
        return RedirectResponse("/", status_code=303)

    if state["current"] >= len(state["order"]):
        return RedirectResponse("/result", status_code=303)

    # Фиксируем момент показа вопроса
    state["started_at"] = time.time()

    q = QUESTIONS[state["order"][state["current"]]]

    response = templates.TemplateResponse(
        request,
        "index.html",
        {
            "q": q,
            "current": state["current"] + 1,
            "total": len(state["order"]),
            "score": state["score"],
            "feedback": None,
            "time_limit": QUESTION_TIME_LIMIT,
        },
    )
    set_state(response, state)  # ← вот этой строки не хватало
    return response


# ---------- Обработка ответа ----------
@app.post("/answer", response_class=HTMLResponse)
async def answer(request: Request, answer: int = Form(-1)):

    state = get_state(request)
    if not state:
        return RedirectResponse("/", status_code=303)

    if state["current"] >= len(state["order"]):
        return RedirectResponse("/result", status_code=303)

    q = QUESTIONS[state["order"][state["current"]]]
    # Проверка таймаута
    started_at = state.get("started_at", 0)
    elapsed = time.time() - started_at
    timed_out = elapsed > QUESTION_TIME_LIMIT

    # answer = -1 означает "клиент не успел / таймер истёк"
    is_correct = (not timed_out) and (answer == q["answer"])

    if is_correct:
        state["score"] += 1

    # Показываем результат сразу, без редиректа
    response = templates.TemplateResponse(
        request,
        "index.html",
        {
            "q": q,
            "current": state["current"] + 1,
            "total": len(state["order"]),
            "score": state["score"],
            "feedback": {
                "chosen": answer,
                "correct": q["answer"],
                "is_correct": is_correct,
                "timed_out": timed_out,

            },
            "time_limit": QUESTION_TIME_LIMIT,

            "next_url": f"/next",
        },
    )

    set_state(response, state)

    return response


# ---------- Переход к следующему вопросу ----------
@app.post("/next")
async def next_question(request: Request):
    state = get_state(request)
    if not state:
        return RedirectResponse("/", status_code=303)

    state["current"] += 1
    state.pop("started_at", None)

    response = RedirectResponse("/question", status_code=303)
    set_state(response, state)
    return response


# ---------- Результат ----------

@app.get("/result", response_class=HTMLResponse)
async def result(request: Request):
    state = get_state(request)
    score = state.get("score", 0) if state else 0
    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "score": score,
            "total": len(QUESTIONS),
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", reload=True)
