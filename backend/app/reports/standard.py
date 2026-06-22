from app.reports.base import ReportRenderer
class StandardReportRenderer(ReportRenderer):
    disclaimer="系统结果仅用于初步筛查，最终以当地文化旅游、行政审批、消防和其他主管部门要求为准。"
    def render(self,r):
        return {"disclaimer":self.disclaimer,"hard_risk":bool(r.get("hard_risks")),"conclusion":r.get("recommendation"),"score":r.get("total_score"),"confidence":r.get("confidence"),"dimensions":r.get("dimensions"),"positive_evidence":r.get("positive_evidence"),"risk_factors":r.get("hard_risks",[])+r.get("negative_evidence",[]),"manual_review":r.get("review_items"),"data_note":"人口相关数量均为 POI 代理指标，不代表真实人口。"}

