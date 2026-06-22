import asyncio,httpx
from app.providers.amap import AmapDataProvider
def test_amap_geocode_mock_response():
    asyncio.run(run_test())
async def run_test():
    def handler(req): return httpx.Response(200,json={"status":"1","geocodes":[{"formatted_address":"北京市东长安街1号","district":"东城区","location":"116.397428,39.90923"}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        data=await AmapDataProvider("secret",client=client).geocode("东长安街1号","北京")
    assert data["coordinate_system"]=="GCJ02"; assert data["longitude"]==116.397428
