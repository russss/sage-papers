import aiohttp
from dateutil.parser import parse as parse_date
from starlette.responses import JSONResponse, StreamingResponse
from starlette.applications import Starlette
from starlette.config import Config
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.exceptions import HTTPException
from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import NotFoundError

config = Config(".env")
DEBUG = config("DEBUG", cast=bool, default=False)

es = AsyncElasticsearch([config("ELASTICSEARCH_URL", cast=str, default="http://localhost:9200")])

templates = Jinja2Templates(directory="templates")

app = Starlette(
    debug=DEBUG,
    routes=[Mount("/static", app=StaticFiles(directory="static"), name="static")],
)


def convert_row(row):
    for key in ("updated_date", "publish_date", "sage_meeting_date"):
        if key in row["_source"] and row["_source"][key] is not None:
            row["_source"][key] = parse_date(row["_source"][key])

    if "attachment" in row["_source"] and "date" in row['_source']['attachment']:
        row["_source"]["attachment"]["date"] = parse_date(
            row["_source"]["attachment"]["date"]
        )
    return row


@app.route("/")
async def main(request):
    recent = await es.search(
        index="sage",
        body={
            "size": 25,
            "_source": [
                "title",
                "publish_date",
                "sage_meeting",
                "sage_meeting_date",
                "attachment.date",
            ],
            "sort": [{"publish_date": "desc"}],
        },
    )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "recent": [convert_row(row) for row in recent["hits"]["hits"]],
        },
    )


@app.route("/meetings")
async def by_meeting(request):
    recent = await es.search(
        index="sage",
        body={
            "size": 1000,
            "_source": [
                "title",
                "publish_date",
                "sage_meeting",
                "sage_meeting_date",
                "attachment.date",
            ],
            "sort": [{"sage_meeting": "desc"}],
        },
    )

    return templates.TemplateResponse(
        "by_meeting.html",
        {
            "request": request,
            "recent": [convert_row(row) for row in recent["hits"]["hits"]],
        },
    )


@app.route("/search")
async def search(request):
    res = await es.search(
        index="sage",
        body={
            "_source": [
                "title",
                "publish_date",
                "sage_meeting_date",
                "attachment.content_type",
            ],
            "query": {
                "multi_match": {
                    "query": request.query_params.get("q"),
                    "fields": ["attachment.content", "title"],
                }
            },
            "highlight": {
                "fields": {
                    "attachment.content": {"number_of_fragments": 3, "order": "score"},
                }
            },
        },
    )
    return JSONResponse(res["hits"])


@app.route("/paper/{id:int}")
async def paper(request):
    paper_id = request.path_params["id"]
    try:
        res = await es.get(index="sage", id=paper_id)
    except NotFoundError:
        raise HTTPException(404, "Paper not found")

    return templates.TemplateResponse("paper.html", {"request": request, "paper": convert_row(res)})


@app.route("/paper_proxy/{id:int}")
async def paper_proxy(request):
    paper_id = request.path_params["id"]
    try:
        res = await es.get(index="sage", id=paper_id)
    except NotFoundError:
        raise HTTPException(404, "Paper not found")

    if "attachment" not in res["_source"]:
        raise HTTPException(404, "No paper for document")

    async def stream_result():
        async with aiohttp.ClientSession() as session:
            async with session.get(res["_source"]["url"]) as resp:
                async for chunk in resp.content:
                    yield chunk

    return StreamingResponse(
        stream_result(), media_type=res["_source"]["attachment"]["content_type"]
    )
