from app.scoring.base import ScoringEngine
class RuleBasedScoringEngine(ScoringEngine):
    def evaluate(self, ctx, cfg):
        pois=ctx.get("pois",[]); prop=ctx.get("property",{}) or {}; weights=cfg["weights"]
        count=lambda *cats: sum(1 for p in pois if p.get("category") in cats)
        transport=min(weights["transport"], count("交通")*4)
        population=min(weights["population_proxy"], count("住宅小区","公寓","宿舍","写字楼")*3)
        competitors=count("竞品"); competition=min(weights["competition"], 6+competitors*2) if competitors else 4
        commercial=min(weights["commercial"], count("商业配套")*2)
        prop_fields=[prop.get(k) for k in ["area_sqm","monthly_rent","floor","street_facing","night_entrance","use_allowed","power_sufficient","fire_confirmed"]]
        filled=sum(v is not None for v in prop_fields); property_score=round(weights["property"]*filled/len(prop_fields),1)
        required=8+len(pois); complete=sum(v is not None for v in prop_fields)+sum(1 for p in pois if p.get("name")); completeness=round(min(100,complete/max(1,required)*100),1)
        dimensions={"交通与可达性":transport,"人口和目标客群代理指标":population,"竞品和市场容量":competition,"商业配套和夜间消费生态":commercial,"物业和租金条件":property_score,"数据完整度":round(weights["completeness"]*completeness/100,1)}
        hard=[]
        for p in pois:
            lim=cfg.get("risk_distance_m",{}).get(p.get("category")); dist=p.get("distance_m")
            if lim and dist is not None and dist<=lim: hard.append({"code":"SENSITIVE_PLACE_DISTANCE","level":"high","message":f"{p['name']}距离约{dist}米，可能不符合准入要求","poi_id":p.get("id")})
        for field,label in [("use_allowed","物业不允许电竞馆业态"),("power_sufficient","供电容量不满足"),("fire_confirmed","消防条件未确认")]:
            if prop.get(field) is False: hard.append({"code":f"PROPERTY_{field.upper()}","level":"high","message":label})
        review=["高架、铁路、河流、绿化带等空间阻隔需人工调查","当地文化旅游、行政审批及消防政策需复核"]
        if not pois: review.append("尚未采集周边 POI")
        total=round(sum(dimensions.values()),1); recommendation="高风险/可能不符合准入" if hard else ("推荐" if total>=cfg["thresholds"]["recommended"] else "谨慎评估" if total>=cfg["thresholds"]["cautious"] else "暂不推荐")
        confidence=round(min(95, completeness*.75 + (10 if pois else 0)),1)
        return {"total_score":total,"recommendation":recommendation,"dimensions":dimensions,"positive_evidence":[f"周边交通 POI {count('交通')} 个",f"商业配套 POI {count('商业配套')} 个"],"negative_evidence":[f"竞品 {competitors} 个"] if competitors else ["竞品数据尚不足"],"hard_risks":hard,"review_items":review,"completeness":completeness,"confidence":confidence,"model_version":cfg["version"]}

