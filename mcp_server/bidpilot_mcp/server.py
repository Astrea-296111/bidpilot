import argparse
import json

from mcp.server.fastmcp import FastMCP

from bidpilot.config import Settings
from bidpilot.mcp_client.approval import verify_approval
from bidpilot.persistence.models import Opportunity
from bidpilot.persistence.repository import Repository

mcp = FastMCP(
    "BidPilot Enterprise MCP",
    host="0.0.0.0",
    port=8001,
    log_level="WARNING",
    stateless_http=True,
    json_response=True,
)


def seed():
    settings = Settings()
    return json.loads((settings.project_root / "data/seed/company.json").read_text(encoding="utf-8"))


@mcp.tool()
def get_company_profile(section: str | None = None) -> dict:
    """Read AuroraSoft's simulated company profile; all data is fictional."""
    profile = seed()["profile"]
    return {"simulated": True, "data": profile.get(section) if section else profile}


@mcp.tool()
def get_product_capability(product: str, capability: str) -> dict:
    """Read structured capabilities for a product. Missing records are not proof of support."""
    products = seed()["products"]
    record = products.get(product, {})
    return {
        "simulated": True,
        "product": product,
        "capabilities": {
            k: v for k, v in record.items() if not capability or k.lower() in capability.lower()
        },
    }


@mcp.tool()
def get_qualification(qualification_name: str) -> dict:
    """Look up an exact certificate; returns found=false for an unrecorded certificate."""
    records = seed()["qualifications"]
    key = qualification_name.lower().replace(" ", "")
    record = next((v for k, v in records.items() if k.lower().replace(" ", "") == key), None)
    return {"simulated": True, "found": record is not None, "record": record}


@mcp.tool()
def get_case_study(industry: str, keyword: str | None = None) -> dict:
    """Return structured case studies by industry with optional keyword filtering."""
    records = [r for r in seed()["cases"] if r["industry"] == industry]
    if keyword:
        records = [
            r for r in records if keyword.casefold() in json.dumps(r, ensure_ascii=False).casefold()
        ]
    return {"simulated": True, "records": records}


@mcp.tool()
def get_historical_bid(industry: str, keyword: str) -> dict:
    """Query historical simulated bids. Past wins do not prove current compliance."""
    return {
        "simulated": True,
        "records": [
            r
            for r in seed()["historical_bids"]
            if r["industry"] == industry
            and keyword.casefold() in json.dumps(r, ensure_ascii=False).casefold()
        ],
    }


@mcp.tool()
async def save_bid_opportunity(
    tender_id: str,
    project_name: str,
    deadline: str | None,
    score: float,
    recommendation: str,
    approval_token: str,
) -> dict:
    """Persist a bid opportunity only with a backend-signed human approval. Idempotent by tender_id."""
    settings = Settings()
    payload = {
        "tender_id": tender_id,
        "project_name": project_name,
        "deadline": deadline,
        "score": score,
        "recommendation": recommendation,
    }
    if not verify_approval(payload, approval_token, settings.approval_secret):
        raise ValueError("Human approval token missing, expired, or mismatched")
    if not 0 <= score <= 100 or recommendation not in {"BID", "CONDITIONAL_BID", "NO_BID"}:
        raise ValueError("Invalid opportunity")
    settings.prepare()
    repository = Repository(settings.database_url)
    try:
        await repository.initialize()
        async with repository.sessions.begin() as session:
            existing = await session.get(Opportunity, tender_id)
            if existing:
                return {"saved": True, "already_existed": True, "tender_id": tender_id}
            session.add(Opportunity(**payload))
        return {"saved": True, "already_existed": False, "tender_id": tender_id}
    finally:
        await repository.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    mcp.settings.port = args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
