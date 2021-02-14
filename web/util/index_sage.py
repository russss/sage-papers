import requests
import logging
import re
from dateutil.parser import parse as parse_date
from time import sleep
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import NotFoundError
from base64 import b64encode

logging.basicConfig(level=logging.INFO)
logging.getLogger("elasticsearch").setLevel(logging.ERROR)
log = logging.getLogger(__name__)

PIPELINE = {
    "description": "Extract attachment information",
    "processors": [{"attachment": {"field": "data"}}, {"remove": {"field": "data"}}],
}

SETTINGS = {
    "mappings": {
        "properties": {
            "updated_date": {"type": "date"},
            "publish_date": {"type": "date"},
            "sage_meeting_date": {"type": "date"},
        }
    }
}

es = Elasticsearch(["http://localhost:9200"])

ROOT = (
    "https://www.gov.uk/api/content/government/collections/"
    "scientific-evidence-supporting-the-government-response-to-coronavirus-covid-19"
)

INDEX_NAME = "sage"
es.ingest.put_pipeline("sage", PIPELINE)
es.indices.create(index=INDEX_NAME, body=SETTINGS, ignore=400)


def fetch_api(url):
    res = requests.get(url)
    res.raise_for_status()
    return res.json()


seen = set()
crawl_stack = [(ROOT, {})]


def trim_doc_title(title):
    return re.sub(r"[-\,] ?[0-9]{1,2} [a-zA-Z]+ [0-9]{4}$", "", title.strip(), re.I).strip()


def index_attachment(attachment, metadata):
    try:
        doc = es.get("sage", attachment["id"])
        if (
            doc
            and "updated_date" in metadata
            and doc["_source"]["updated_date"] == metadata["updated_date"]
        ):
            return
    except NotFoundError:
        pass

    es_doc = {
        "title": trim_doc_title(attachment["title"]),
        "url": attachment["url"],
        "pages_count": attachment.get("number_of_pages"),
    }

    log.info('Indexing %s "%s"', attachment['title'], es_doc["title"])

    es_doc.update(metadata)
    pipeline = None
    if attachment.get("content_type") == "application/pdf":
        pdf_req = requests.get(attachment["url"])
        pdf_req.raise_for_status()
        es_doc["data"] = b64encode(pdf_req.content)
        pipeline = "sage"

    es.index(index="sage", id=attachment["id"], pipeline=pipeline, body=es_doc)


def attachments_by_id(doc):
    result = {}

    for link in doc.get("links", {}).get("documents", []):
        result[link["content_id"]] = link
    return result


def parse_group_title(title):
    match = re.match(r"Meeting ([0-9]+), (.*)", title, re.I)
    if match:
        return {
            "sage_meeting": int(match.group(1)),
            "sage_meeting_date": parse_date(match.group(2)),
        }
    else:
        return {"section": title}


def crawl(url, metadata):
    doc = fetch_api(url)

    if (
        "sage meetings" in doc["title"].lower()
        and len(doc["details"]["collection_groups"]) > 0
    ):
        # Need to use the "collection_groups" to extract which
        # SAGE meeting this relates to and pass it through.

        by_id = attachments_by_id(doc)
        for group in doc["details"]["collection_groups"]:
            for doc_id in group["documents"]:
                if doc_id not in by_id:
                    continue
                link = by_id[doc_id]
                crawl_stack.append((link["api_url"], parse_group_title(group["title"])))
    else:
        for link in doc.get("links", {}).get("documents", []):
            crawl_stack.append((link["api_url"], {}))

    attachments = doc.get("details", {}).get("attachments", [])

    doc_metadata = {
        "publish_date": doc["first_published_at"],
        "updated_date": doc["public_updated_at"],
        "from": "sage"
    }
    doc_metadata.update(metadata)

    for attachment in attachments:
        index_attachment(attachment, doc_metadata)


log.info("Starting crawl...")
while len(crawl_stack) > 0:
    data = crawl_stack.pop()
    if data[0] in seen:
        continue
    try:
        crawl(*data)
    except Exception:
        log.error("Error on crawl: %s", data)
        raise
    sleep(0.2)

log.info("Crawl complete.")
