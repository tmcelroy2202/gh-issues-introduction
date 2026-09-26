from contextlib import asynccontextmanager
import sqlite3

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, field_validator

from database import get_all_introductions, get_base_site_url, initialize_database, upsert_introduction
from scraper import ScrapeError, fetch_introduction_json, username_from_json_url


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="ITIS3135 Introduction JSON API",
    description=(
        "Fetches introduction JSON exports hosted on webpages.charlotte.edu and "
        "stores one updatable record per Charlotte username."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


class JSONURLSubmission(BaseModel):
    json_url: str

    @field_validator("json_url")
    @classmethod
    def validate_json_url(cls, value: str) -> str:
        value = value.strip()
        try:
            username_from_json_url(value)
        except ValueError as error:
            raise ValueError(str(error)) from error
        return value


@app.get("/sites", response_model=dict[str, dict], summary="Get all saved introductions")
@app.get("/", response_model=dict[str, dict], include_in_schema=False)
def list_introductions() -> dict:
    try:
        return get_all_introductions()
    except sqlite3.Error as error:
        raise HTTPException(status_code=500, detail="Could not read the introduction database.") from error


async def save_json_url(json_url: str, response: Response, is_put: bool = False) -> dict:
    username = username_from_json_url(json_url)
    try:
        data = await fetch_introduction_json(json_url)
    except ScrapeError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error

    try:
        updated_at, created = upsert_introduction(username, json_url, data)
    except sqlite3.Error as error:
        raise HTTPException(status_code=500, detail="Could not save the introduction in SQLite.") from error

    if not is_put and not created:
        response.status_code = 200
    return {
        "username": username,
        "lastUpdated": updated_at,
        "jsonUrl": json_url,
        "baseSiteUrl": get_base_site_url(json_url, username),
        "introductionData": data,
    }


@app.post("/sites", status_code=201, summary="Fetch and save an introduction JSON URL")
@app.post("/", status_code=201, include_in_schema=False)
async def post_introduction(submission: JSONURLSubmission, response: Response) -> dict:
    return await save_json_url(submission.json_url, response)


@app.put("/sites", summary="Refresh a username's introduction JSON")
@app.put("/", include_in_schema=False)
async def put_introduction(submission: JSONURLSubmission, response: Response) -> dict:
    return await save_json_url(submission.json_url, response, is_put=True)
