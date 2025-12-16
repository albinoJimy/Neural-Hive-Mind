import httpx


async def query_prometheus(prometheus_url: str, query: str):
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"http://{prometheus_url}/api/v1/query", params={"query": query})
        resp.raise_for_status()
        return resp.json()


async def get_metric_value(prometheus_url: str, metric_name: str, labels=None):
    label_str = ""
    if labels:
        pairs = [f'{k}="{v}"' for k, v in labels.items()]
        label_str = "{" + ",".join(pairs) + "}"
    query = f"{metric_name}{label_str}"
    data = await query_prometheus(prometheus_url, query)
    results = data.get("data", {}).get("result", [])
    if not results:
        return None
    return results[0]["value"][1]
