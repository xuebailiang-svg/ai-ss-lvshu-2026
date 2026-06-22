from datetime import datetime, timezone
import httpx
from app.providers.base import DataProvider

class ProviderError(RuntimeError): pass
class AmapDataProvider(DataProvider):
    base_url="https://restapi.amap.com/v3"
    def __init__(self, key: str, client: httpx.AsyncClient|None=None, mock: bool=False): self.key=key; self.client=client; self.mock=mock
    async def _get(self, path, params):
        if not self.key: raise ProviderError("AMAP_WEB_SERVICE_KEY is not configured")
        owns=self.client is None; client=self.client or httpx.AsyncClient(timeout=15)
        try:
            r=await client.get(f"{self.base_url}/{path}", params={**params,"key":self.key}); r.raise_for_status(); data=r.json()
            if data.get("status") != "1": raise ProviderError(f"Amap API failed: {data.get('info','unknown error')} ({data.get('infocode','')})")
            return data
        except httpx.HTTPError as e: raise ProviderError(f"Amap HTTP request failed: {type(e).__name__}") from e
        finally:
            if owns: await client.aclose()
    async def geocode(self,address,city=None):
        if self.mock: return {"formatted_address":f"{city or ''}{address}","district":city or "测试区","longitude":116.397428,"latitude":39.90923,"coordinate_system":"GCJ02","provider":"amap"}
        d=await self._get("geocode/geo",{"address":address,"city":city or ""}); rows=d.get("geocodes",[])
        if not rows: raise ProviderError("Amap geocode returned no result")
        row=rows[0]; lng,lat=map(float,row["location"].split(",")); return {"formatted_address":row.get("formatted_address",address),"district":row.get("district") or row.get("adcode"),"longitude":lng,"latitude":lat,"coordinate_system":"GCJ02","provider":"amap"}
    async def search_nearby(self,longitude,latitude,radius,categories):
        if self.mock:
            return [{"source":"amap","provider_record_id":"mock-school-1","name":"示例中学","category":"中学","type_code":"141200","address":"候选点附近","longitude":longitude+.001,"latitude":latitude+.001,"distance_m":160,"phone":None,"business_hours":None,"business_area":None,"observed_at":datetime.now(timezone.utc),"fetched_at":datetime.now(timezone.utc),"confidence":.6,"is_estimated":True,"needs_verification":True,"raw_data":{"mock":True}}]
        keywords="|".join(categories); d=await self._get("place/around",{"location":f"{longitude},{latitude}","radius":radius,"keywords":keywords,"offset":25,"extensions":"all"})
        out=[]
        for p in d.get("pois",[]):
            try: lng,lat=map(float,p["location"].split(","))
            except (KeyError,ValueError): continue
            out.append({"source":"amap","provider_record_id":p["id"],"name":p.get("name","未知"),"category":self._category(p),"type_code":p.get("typecode"),"address":self._text(p.get("address")),"longitude":lng,"latitude":lat,"distance_m":int(p["distance"]) if str(p.get("distance","")).isdigit() else None,"phone":self._text(p.get("tel")),"business_hours":(p.get("biz_ext") or {}).get("open_time"),"business_area":self._text(p.get("business_area")),"observed_at":datetime.now(timezone.utc),"fetched_at":datetime.now(timezone.utc),"confidence":.75,"is_estimated":False,"needs_verification":False,"raw_data":p})
        return out
    async def get_place_detail(self,provider_place_id): return await self._get("place/detail",{"id":provider_place_id,"extensions":"all"})
    @staticmethod
    def _text(v): return v if isinstance(v,str) else None
    @staticmethod
    def _category(p):
        n=f"{p.get('name','')} {p.get('type','')}"; groups=[("竞品",["网吧","网咖","电竞"]),("小学",["小学"]),("中学",["中学"]),("幼儿园",["幼儿园"]),("大学",["大学","学院"]),("交通",["地铁","公交","停车"]),("商业配套",["商场","餐饮","便利店","KTV","酒吧","酒店"])]
        return next((g for g,ks in groups if any(k in n for k in ks)),"其他")

