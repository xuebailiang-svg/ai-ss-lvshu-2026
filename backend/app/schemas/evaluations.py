from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
class PropertyIn(BaseModel):
    area_sqm: float|None=None; monthly_rent: float|None=None; floor: str|None=None; street_facing: bool|None=None; night_entrance: bool|None=None; use_allowed: bool|None=None; power_sufficient: bool|None=None; fire_confirmed: bool|None=None; notes: str|None=None
class EvaluationCreate(BaseModel):
    name: str=Field(min_length=1,max_length=120); city: str=Field(min_length=1,max_length=50); address: str=Field(min_length=1,max_length=300); radius: int=Field(3000,ge=100,le=50000); property: PropertyIn=PropertyIn()
class SiteOut(BaseModel):
    model_config=ConfigDict(from_attributes=True); formatted_address:str|None; district:str|None; longitude:float|None; latitude:float|None; coordinate_system:str; provider:str
class EvaluationOut(BaseModel):
    model_config=ConfigDict(from_attributes=True); id:int; name:str; city:str; address:str; radius:int; status:str; error_message:str|None; created_at:datetime; site:SiteOut|None=None
class CompetitorEnrichmentIn(BaseModel):
    opened_at_estimate:str|None=None; machine_count:int|None=Field(None,ge=0); area_sqm:float|None=Field(None,ge=0); hardware:dict={}; pricing:dict={}; occupancy:dict={}; source:str|None=None; confidence:float=Field(.5,ge=0,le=1); notes:str|None=None

