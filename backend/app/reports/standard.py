from app.reports.base import ReportRenderer


class StandardReportRenderer(ReportRenderer):
    disclaimer = "系统结果仅用于初步选址调研，最终以当地行政审批、消防、文旅和其他主管部门要求为准。"

    def render(self, result, ctx=None):
        evaluation = (ctx or {}).get("evaluation", {})
        pois = [self._public_poi(poi) for poi in evaluation.get("pois", [])]
        pois = self._sort_by_distance(pois)
        prop = ((evaluation.get("site") or {}).get("property") or {})
        poi_statistics = evaluation.get("poi_statistics") or {}
        competitors = [poi for poi in pois if poi.get("business_category") == "竞品"]
        enriched = [poi for poi in competitors if self._has_supplement(poi)]
        traffic = [poi for poi in pois if poi.get("business_category") == "交通"]
        sensitive = [poi for poi in pois if poi.get("business_category") == "敏感场所"]
        population = [poi for poi in pois if poi.get("business_category") == "住宅"]
        commercial = [poi for poi in pois if poi.get("business_category") in {"餐饮", "娱乐", "夜间配套"}]
        category_summary = self._category_summary(pois)
        competitor_checklist = self._competitor_checklist(competitors)
        surroundings = self._poi_checklist(
            commercial,
            {
                "餐饮": ["餐饮", "美食", "饭店", "餐厅"],
                "奶茶": ["奶茶", "饮品", "茶饮"],
                "便利店": ["便利店", "超市"],
                "KTV": ["KTV", "歌厅"],
                "酒吧": ["酒吧"],
                "台球厅": ["台球"],
                "电影院": ["电影院", "电影"],
                "酒店": ["酒店", "宾馆"],
                "夜间消费场景": ["KTV", "酒吧", "台球", "电影院", "电影", "密室", "夜市"],
            },
        )
        traffic_checklist = self._poi_checklist(
            traffic,
            {
                "地铁": ["地铁"],
                "公交": ["公交"],
                "停车": ["停车"],
                "主干道": ["路", "街", "大道"],
                "隔离带/高架/铁路等不利因素": ["高架", "铁路", "隔离带", "河流", "绿化带"],
            },
        )
        population_checklist = self._poi_checklist(
            population,
            {
                "住宅小区": ["住宅小区", "小区", "居民区"],
                "公寓": ["公寓"],
                "写字楼": ["写字楼", "办公楼", "商务楼"],
                "大学": ["大学", "学院"],
                "中职": ["中职", "职业"],
                "技校": ["技校", "技工"],
                "医院": ["医院"],
            },
        )
        sensitive_checklist = self._poi_checklist(
            sensitive,
            {
                "小学": ["小学"],
                "中学": ["中学"],
                "幼儿园": ["幼儿园"],
                "政府机构": ["政府", "机关", "政务"],
                "医院": ["医院"],
                "需核实距离": ["小学", "中学", "幼儿园", "政府", "医院"],
            },
        )
        property_checklist = self._property_checklist(prop)
        infrastructure_checklist = self._infrastructure_checklist(prop)
        manual_checklist = self._manual_checklist(
            competitor_checklist,
            surroundings,
            traffic_checklist,
            population_checklist,
            sensitive_checklist,
            property_checklist,
            infrastructure_checklist,
            result.get("review_items", []),
        )

        return {
            "disclaimer": self.disclaimer,
            "hard_risk": bool(result.get("hard_risks")),
            "conclusion": result.get("recommendation"),
            "score": result.get("total_score"),
            "dimensions": result.get("dimensions"),
            "positive_evidence": result.get("positive_evidence"),
            "risk_factors": result.get("hard_risks", []) + result.get("negative_evidence", []),
            "manual_review": result.get("review_items"),
            "data_note": "人口相关数量均为 POI 代理指标，不代表真实人口；人工估算数据会明确标注为估算值。",
            "sections": {
                "summary": {
                    "title": "结论摘要",
                    "recommendation": result.get("recommendation"),
                    "score": result.get("total_score"),
                    "basis": result.get("positive_evidence", []) + result.get("negative_evidence", []),
                },
                "hard_risks": {"title": "硬性风险", "items": result.get("hard_risks", [])},
                "score": {"title": "综合评分", "dimensions": result.get("dimensions", {})},
                "dimension_scores": {"title": "各维度得分", "items": [{"name": k, "score": v} for k, v in (result.get("dimensions") or {}).items()]},
                "quality": {
                    "title": "数据完整度和核实状态",
                    "completeness": result.get("completeness"),
                    "manual_competitor_records": len(enriched),
                },
                "poi_category_summary": {"title": "POI 分类补充统计", "items": category_summary},
                "poi_statistics": {"title": "POI 分类统计", "items": poi_statistics},
                "competitors": {
                    "title": "竞品分析",
                    "auto_collected_count": len(competitors),
                    "manual_survey_count": len(enriched),
                    "items": [self._competitor_item(poi) for poi in competitors],
                    "checklist": competitor_checklist,
                },
                "surroundings": {"title": "周边配套", "auto_collected_count": len(commercial), "checklist": surroundings},
                "traffic": {"title": "交通与可达性", "auto_collected_count": len(traffic), "items": self._brief(traffic), "checklist": traffic_checklist},
                "sensitive_places": {"title": "敏感场所与合规", "auto_collected_count": len(sensitive), "items": self._brief(sensitive), "checklist": sensitive_checklist},
                "population_proxy": {
                    "title": "人口代理指标",
                    "auto_collected_count": len(population),
                    "note": "这是基于住宅、公寓、写字楼、大学、中职、技校等 POI 的代理指标，不是真实人口。",
                    "items": self._brief(population),
                    "checklist": population_checklist,
                },
                "commercial": {"title": "商业配套", "auto_collected_count": len(commercial), "items": self._brief(commercial), "checklist": surroundings},
                "property_cost": {
                    "title": "物业与成本",
                    "manual_data": prop,
                    "rent_summary": {
                        "monthly_rent": prop.get("monthly_rent"),
                        "rent_per_sqm_month": prop.get("rent_per_sqm_month"),
                        "rent_per_sqm_day": prop.get("rent_per_sqm_day"),
                        "rent_per_machine_month": prop.get("rent_per_machine_month"),
                    },
                    "checklist": property_checklist,
                },
                "infrastructure": {"title": "消防、供电、网络、夜间入口", "checklist": infrastructure_checklist},
                "review_items": {"title": "待人工核实事项", "items": result.get("review_items", [])},
                "manual_checklist": {"title": "人工核实清单", "items": manual_checklist},
                "next_steps": {
                    "title": "下一步调研建议",
                    "items": [
                        "现场复核竞品价格、机器配置、机器数量和高峰/平峰上座率。",
                        "核实候选物业是否允许电竞馆/网咖业态及消防审批路径。",
                        "确认供电容量、网络双线路、独立夜间出入口和噪声投诉风险。",
                        "核实地铁/公交/停车可达性，以及高架、铁路、隔离带等空间阻隔。",
                        "补充租金、物业费、转让费、押金、免租期等成本证明材料。",
                    ],
                },
                "data_sources": {
                    "title": "数据来源",
                    "auto": ["高德地图 Web 服务 POI / Geocode"],
                    "manual": ["竞品调研表", "物业调查表"],
                    "estimated": ["人口代理指标", "人工填写的上座率估算值"],
                    "unverified": [item for item in result.get("review_items", [])],
                },
                "scoring_rules": {
                    "title": "评分规则说明",
                    "model_version": result.get("model_version"),
                    "note": "硬性风险与普通评分分离，高分不能覆盖准入风险。",
                },
            },
        }

    @staticmethod
    def _brief(rows):
        rows = StandardReportRenderer._sort_by_distance(rows)
        return [
            {
                "poi_id": row.get("poi_id") or row.get("id"),
                "name": row.get("name"),
                "business_category": row.get("business_category"),
                "subcategory": row.get("subcategory"),
                "address": row.get("address"),
                "distance_m": row.get("distance_m"),
                "walking_distance_m": row.get("walking_distance_m"),
                "walking_time_min": row.get("walking_time_min"),
                "data_source": row.get("data_source"),
                "verification_status": row.get("verification_status"),
                "missing_items": row.get("missing_items"),
                "notes": row.get("notes"),
            }
            for row in rows[:20]
        ]

    @staticmethod
    def _competitor_item(poi):
        enrichment = poi.get("supplement") or {}
        occupancy = {
            "peak_occupancy_rate": enrichment.get("peak_occupancy_rate"),
            "offpeak_occupancy_rate": enrichment.get("offpeak_occupancy_rate"),
            "weekday_daytime_occupancy": enrichment.get("weekday_daytime_occupancy"),
            "weekday_evening_occupancy": enrichment.get("weekday_evening_occupancy"),
            "weekend_daytime_occupancy": enrichment.get("weekend_daytime_occupancy"),
            "weekend_evening_occupancy": enrichment.get("weekend_evening_occupancy"),
            "label": "估算值" if enrichment.get("peak_occupancy_rate") is not None or enrichment.get("offpeak_occupancy_rate") is not None else None,
        }
        return {
            "poi_id": poi.get("poi_id") or poi.get("id"),
            "name": poi.get("name"),
            "distance_m": poi.get("distance_m"),
            "amap_data": {"address": poi.get("address"), "business_category": poi.get("business_category"), "subcategory": poi.get("subcategory")},
            "manual_data": enrichment or None,
            "occupancy": occupancy,
            "verified": poi.get("verification_status") == "已人工核实",
        }

    @classmethod
    def _competitor_checklist(cls, competitors):
        return [
            cls._check_item("已采集竞品", bool(competitors), "自动采集", cls._brief(competitors), "未采集到竞品，建议扩大半径或现场核查周边门店。"),
            cls._check_item("待补充竞品价格", all((poi.get("supplement") or {}).get("normal_price") is not None for poi in competitors) if competitors else False, "人工填写", [], "补充普通区/高配区/包间/会员价格。"),
            cls._check_item("待补充机器配置", all((poi.get("supplement") or {}).get("cpu") or (poi.get("supplement") or {}).get("gpu") for poi in competitors) if competitors else False, "人工填写", [], "补充 CPU、显卡、显示器尺寸和刷新率。"),
            cls._check_item("待补充机器数量", all((poi.get("supplement") or {}).get("machine_count") is not None for poi in competitors) if competitors else False, "人工填写", [], "补充机器数量，用于判断竞品强度。"),
            cls._check_item("待补充上座率", all((poi.get("supplement") or {}).get("peak_occupancy_rate") is not None or (poi.get("supplement") or {}).get("weekday_evening_occupancy") for poi in competitors) if competitors else False, "估算", [], "现场观察高峰/平峰上座率，并标注为估算值。"),
            cls._check_item("待补充充值活动", all((poi.get("supplement") or {}).get("recharge_promotion") for poi in competitors) if competitors else False, "人工填写", [], "补充会员充值和促销活动。"),
            cls._check_item("待补充开业年限", all((poi.get("supplement") or {}).get("opened_at_estimate") or (poi.get("supplement") or {}).get("opening_years") for poi in competitors) if competitors else False, "估算", [], "通过点评记录、招牌、访谈等估算开业时间。"),
        ]

    @classmethod
    def _poi_checklist(cls, rows, spec):
        return [cls._check_item(label, bool(matches := cls._match_pois(rows, keywords)), "自动采集", cls._brief(matches), "未采集到，建议现场确认。") for label, keywords in spec.items()]

    @classmethod
    def _property_checklist(cls, prop):
        fields = [
            ("面积", ["area_sqm", "usable_area_sqm"], "建筑面积和实际使用面积"),
            ("月租金", ["monthly_rent"], "月总租金"),
            ("元/㎡/月", ["rent_per_sqm_month"], "单位月租金"),
            ("元/㎡/天", ["rent_per_sqm_day"], "单位日租金"),
            ("转让费", ["transfer_fee"], "转让费"),
            ("物业费", ["property_fee_monthly"], "物业费"),
            ("押金", ["deposit"], "押金"),
            ("免租期", ["rent_free_months"], "免租期"),
            ("每台机器分摊租金", ["rent_per_machine_month"], "每台机器分摊月租金"),
            ("数据来源", ["source"], "物业数据来源"),
        ]
        items = []
        for label, keys, note in fields:
            complete = any(prop.get(key) not in (None, "") for key in keys)
            values = {key: prop.get(key) for key in keys if prop.get(key) not in (None, "")}
            items.append(cls._check_item(label, complete, "人工填写", values, f"{note}待人工核实。"))
        items.append(cls._check_item("需要人工核实项", bool(prop.get("required_rectifications") or prop.get("notes")), "人工填写", prop.get("required_rectifications") or prop.get("notes"), "补充整改事项、联系人和证明材料。"))
        return items

    @classmethod
    def _infrastructure_checklist(cls, prop):
        fields = [
            ("消防条件", "fire_confirmed", "确认消防条件、喷淋、排烟、安全出口。"),
            ("供电容量", "power_sufficient", "确认供电容量是否满足机器数量和空调负载。"),
            ("网络条件", "network_carriers", "确认运营商和双线路。"),
            ("独立夜间入口", "night_entrance", "确认夜间独立出入口和物业管理要求。"),
            ("允许电竞馆/网咖业态", "use_allowed", "确认租赁合同和物业业态许可。"),
        ]
        return [cls._check_item(label, prop.get(key) not in (None, "", False), "人工填写", prop.get(key), note) for label, key, note in fields]

    @classmethod
    def _manual_checklist(cls, *groups):
        items = []
        for group in groups:
            if isinstance(group, list):
                for item in group:
                    if isinstance(item, dict) and item.get("status") != "已确认":
                        items.append(item.get("name") or item.get("note"))
                    elif isinstance(item, str):
                        items.append(item)
        return [item for item in items if item]

    @staticmethod
    def _match_pois(rows, keywords):
        matches = []
        for row in rows:
            text = f"{row.get('name', '')} {row.get('business_category', '')} {row.get('subcategory', '')} {row.get('address', '')}"
            if any(keyword in text for keyword in keywords):
                matches.append(row)
        return matches

    @staticmethod
    def _sort_by_distance(rows):
        def key(row):
            distance = row.get("distance_m")
            try:
                distance = int(float(distance))
            except (TypeError, ValueError):
                distance = None
            return (distance is None, distance if distance is not None else 10**12, str(row.get("name") or ""))

        return sorted(rows, key=key)

    @staticmethod
    def _public_poi(poi):
        public = poi.get("public") or {}
        if public:
            return public
        return {
            "poi_id": poi.get("id"),
            "id": poi.get("id"),
            "name": poi.get("name"),
            "business_category": poi.get("category"),
            "subcategory": poi.get("category"),
            "address": poi.get("address"),
            "distance_m": poi.get("distance_m"),
            "data_source": "高德" if poi.get("source") == "amap" else "人工",
            "verification_status": "已人工核实" if poi.get("is_manually_verified") else "未核实",
            "missing_items": [],
            "missing_items_text": "",
            "supplement": poi.get("enrichment") or {},
            "is_manual": poi.get("source") == "manual",
        }

    @staticmethod
    def _has_supplement(poi):
        supplement = poi.get("supplement") or {}
        useful = {key: value for key, value in supplement.items() if key not in {"subcategory"} and value not in (None, "", [], {})}
        return bool(useful)

    @classmethod
    def _category_summary(cls, pois):
        categories = ["竞品", "住宅", "交通", "娱乐", "餐饮", "夜间配套", "敏感场所", "物业线索", "其他"]
        items = []
        for category in categories:
            rows = [poi for poi in pois if poi.get("business_category") == category]
            if not rows:
                items.append({
                    "category": category,
                    "auto_count": 0,
                    "manual_count": 0,
                    "enriched_count": 0,
                    "verified_count": 0,
                    "missing_fields": ["未采集到，建议现场确认"],
                })
                continue
            missing = []
            for row in rows:
                missing.extend(row.get("missing_items") or [])
            items.append({
                "category": category,
                "auto_count": sum(1 for row in rows if row.get("data_source") == "高德"),
                "manual_count": sum(1 for row in rows if row.get("is_manual") or row.get("data_source") != "高德"),
                "enriched_count": sum(1 for row in rows if cls._has_supplement(row)),
                "verified_count": sum(1 for row in rows if row.get("verification_status") == "已人工核实"),
                "missing_fields": sorted(set(missing))[:20],
            })
        return items

    @staticmethod
    def _check_item(name, complete, data_type, value, note):
        return {
            "name": name,
            "status": "已确认" if complete else "待人工核实",
            "data_type": data_type if complete else "未核实",
            "value": value,
            "note": note if not complete else "",
        }
