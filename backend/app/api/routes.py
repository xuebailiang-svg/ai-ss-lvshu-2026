from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
import yaml
from app.core.config import get_settings
from app.core.database import get_db
from app.models import *
from app.providers.amap import AmapDataProvider, ProviderError
from app.reports.standard import StandardReportRenderer
from app.schemas import EvaluationCreate, EvaluationOut, CompetitorEnrichmentIn
from app.scoring.rule_based import RuleBasedScoringEngine

router=APIRouter(prefix="/api")
def provider():
    s=get_settings(); return AmapDataProvider(s.amap_web_service_key,mock=s.amap_mock)
def evaluation_or_404(db,id):
    ev=db.scalar(select(SiteEvaluation).where(SiteEvaluation.id==id).options(selectinload(SiteEvaluation.site).selectinload(CandidateSite.property_survey),selectinload(SiteEvaluation.pois),selectinload(SiteEvaluation.result)))
    if not ev: raise HTTPException(404,"Evaluation not found")
    return ev
@router.get("/health")
def health(db:Session=Depends(get_db)):
    db.execute(select(1)); return {"status":"ok","service":"esports-site-selection","database":"connected"}
@router.post("/evaluations",response_model=EvaluationOut,status_code=201)
def create_evaluation(body:EvaluationCreate,db:Session=Depends(get_db)):
    ev=SiteEvaluation(name=body.name,city=body.city,address=body.address,radius=body.radius); site=CandidateSite(); site.property_survey=PropertySurvey(**body.property.model_dump()); ev.site=site; db.add(ev); db.commit(); return evaluation_or_404(db,ev.id)
@router.get("/evaluations",response_model=list[EvaluationOut])
def list_evaluations(city:str|None=None,q:str|None=None,db:Session=Depends(get_db)):
    stmt=select(SiteEvaluation).options(selectinload(SiteEvaluation.site)).order_by(SiteEvaluation.created_at.desc())
    if city: stmt=stmt.where(SiteEvaluation.city.contains(city))
    if q: stmt=stmt.where(SiteEvaluation.address.contains(q))
    return list(db.scalars(stmt))
@router.get("/evaluations/{id}")
def get_evaluation(id:int,db:Session=Depends(get_db)):
    ev=evaluation_or_404(db,id); return serialize(ev)
@router.post("/evaluations/{id}/geocode")
async def geocode(id:int,db:Session=Depends(get_db)):
    ev=evaluation_or_404(db,id); ev.status=JobStatus.running; db.commit()
    try:
        data=await provider().geocode(ev.address,ev.city)
        for k,v in data.items(): setattr(ev.site,k,v)
        ev.status=JobStatus.completed; ev.error_message=None; db.commit(); return data
    except ProviderError as e:
        ev.status=JobStatus.failed; ev.error_message=str(e); db.commit(); raise HTTPException(502,str(e))
@router.post("/evaluations/{id}/collect-pois")
async def collect_pois(id:int,db:Session=Depends(get_db)):
    ev=evaluation_or_404(db,id)
    if ev.site.longitude is None: raise HTTPException(409,"Please geocode the candidate site first")
    ev.status=JobStatus.running; db.commit()
    cats=["网吧","网咖","电竞馆","电竞酒店","小学","中学","幼儿园","大学","中职","技校","政府机构","医院","地铁站","公交站","停车场","住宅小区","公寓","宿舍","写字楼","商场","餐饮","奶茶","便利店","KTV","酒吧","台球厅","电影院","密室逃脱","酒店","夜市"]
    try:
        rows=await provider().search_nearby(ev.site.longitude,ev.site.latitude,ev.radius,cats)
        for old in list(ev.pois): db.delete(old)
        db.flush()
        for row in rows: db.add(PoiObservation(evaluation_id=ev.id,**row))
        ev.status=JobStatus.completed; ev.error_message=None; db.commit(); return {"status":"completed","count":len(rows)}
    except ProviderError as e:
        ev.status=JobStatus.failed; ev.error_message=str(e); db.commit(); raise HTTPException(502,str(e))
@router.post("/evaluations/{id}/score")
def score(id:int,db:Session=Depends(get_db)):
    ev=evaluation_or_404(db,id); path=Path(get_settings().scoring_config_path)
    if not path.is_absolute(): path=Path(__file__).parents[1]/"scoring"/"default.yaml"
    cfg=yaml.safe_load(path.read_text(encoding="utf-8")); pois=[poi_dict(p) for p in ev.pois]; prop=ev.site.property_survey
    result=RuleBasedScoringEngine().evaluate({"pois":pois,"property":property_dict(prop)},cfg)
    if ev.result:
        for k,v in result.items(): setattr(ev.result,k,v)
    else: db.add(ScoringResult(evaluation_id=id,**result))
    db.flush(); report=StandardReportRenderer().render(result); existing=db.scalar(select(EvaluationReport).where(EvaluationReport.evaluation_id==id))
    if existing: existing.content=report
    else: db.add(EvaluationReport(evaluation_id=id,renderer="standard",content=report))
    db.commit(); return result
@router.get("/evaluations/{id}/report")
def report(id:int,db:Session=Depends(get_db)):
    evaluation_or_404(db,id); row=db.scalar(select(EvaluationReport).where(EvaluationReport.evaluation_id==id))
    if not row: raise HTTPException(409,"Please score the evaluation first")
    return row.content
@router.put("/competitors/{id}/enrichment")
def enrich(id:int,body:CompetitorEnrichmentIn,db:Session=Depends(get_db)):
    poi=db.get(PoiObservation,id)
    if not poi or poi.category!="竞品": raise HTTPException(404,"Competitor POI not found")
    row=db.scalar(select(CompetitorEnrichment).where(CompetitorEnrichment.poi_observation_id==id))
    if row:
        for k,v in body.model_dump().items(): setattr(row,k,v)
    else: row=CompetitorEnrichment(poi_observation_id=id,**body.model_dump()); db.add(row)
    db.commit(); db.refresh(row); return {"id":row.id,"poi_observation_id":id,**body.model_dump()}
@router.get("/regulation-rules")
def rules(db:Session=Depends(get_db)):
    rows=list(db.scalars(select(RegulationRule).where(RegulationRule.enabled==True)))
    if rows: return rows
    return [{"city":"*","sensitive_type":"小学/中学","limit_distance_m":200,"calculation_method":"provider_distance","risk_level":"high","policy_basis":"示例初筛规则，须以当地现行政策为准","manual_review":True}]
def property_dict(p): return {c.name:getattr(p,c.name) for c in p.__table__.columns if c.name not in ("id","candidate_site_id")} if p else {}
def poi_dict(p): return {c.name:getattr(p,c.name) for c in p.__table__.columns if c.name not in ("raw_data",)}
def serialize(ev):
    return {"id":ev.id,"name":ev.name,"city":ev.city,"address":ev.address,"radius":ev.radius,"status":ev.status,"error_message":ev.error_message,"created_at":ev.created_at,"site":({"id":ev.site.id,"formatted_address":ev.site.formatted_address,"district":ev.site.district,"longitude":ev.site.longitude,"latitude":ev.site.latitude,"coordinate_system":ev.site.coordinate_system,"provider":ev.site.provider,"property":property_dict(ev.site.property_survey)} if ev.site else None),"pois":[poi_dict(p) for p in ev.pois],"result":({c.name:getattr(ev.result,c.name) for c in ev.result.__table__.columns} if ev.result else None)}

