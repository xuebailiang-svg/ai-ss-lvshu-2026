export type PropertySurvey = {
  area_sqm?: number;
  usable_area_sqm?: number;
  monthly_rent?: number;
  rent_per_sqm_day?: number;
  rent_per_sqm_month?: number;
  floor?: string;
  floor_height_m?: number;
  property_fee_monthly?: number;
  transfer_fee?: number;
  deposit?: number;
  rent_free_months?: number;
  lease_term_months?: number;
  rent_escalation?: string;
  power_capacity_kw?: number;
  power_expansion_allowed?: boolean;
  network_carriers?: string;
  dual_line_supported?: boolean;
  night_entrance?: boolean;
  use_allowed?: boolean;
  fire_confirmed?: boolean;
  sprinkler?: boolean;
  smoke_exhaust?: boolean;
  safety_exit_count?: number;
  parking_condition?: string;
  facade_width_m?: number;
  street_facing?: boolean;
  facade_visibility?: string;
  noise_complaint_risk?: string;
  required_rectifications?: string;
  property_contact?: string;
  machine_count?: number;
  rent_per_machine_month?: number;
  power_sufficient?: boolean;
  surveyed_at?: string;
  source?: string;
  confidence?: number;
  verified_at?: string;
  notes?: string;
};

export type CompetitorEnrichment = {
  machine_count?: number;
  area_sqm?: number;
  cpu?: string;
  gpu?: string;
  monitor_size_inch?: number;
  monitor_refresh_rate?: number;
  normal_price?: number;
  premium_price?: number;
  private_room_price?: number;
  member_price?: number;
  recharge_promotion?: string;
  opened_at_estimate?: string;
  opening_basis?: string;
  peak_occupancy_rate?: number;
  offpeak_occupancy_rate?: number;
  surveyed_at?: string;
  survey_method?: string;
  source?: string;
  confidence?: number;
  verified_at?: string;
  is_manually_verified?: boolean;
  notes?: string;
};

export type Evaluation = {
  id: number;
  name: string;
  city: string;
  address: string;
  radius: number;
  status: string;
  error_message?: string;
  created_at: string;
  updated_at?: string;
  site?: {
    formatted_address?: string;
    district?: string;
    longitude?: number;
    latitude?: number;
    coordinate_system: string;
    provider: string;
    property?: PropertySurvey;
  };
  pois?: Poi[];
  result?: Score;
};

export type PoiTemplateField = {
  key: string;
  label: string;
};

export type PoiTemplate = {
  export_key: string;
  sub_label: string;
  fields: PoiTemplateField[];
  required_labels: string[];
  subtype_templates?: Record<string, string[]>;
};

export type PoiTemplates = {
  base_columns: PoiTemplateField[];
  categories: Record<string, PoiTemplate>;
};

export type PoiPublic = {
  poi_id: number;
  id: number;
  name: string;
  business_category: string;
  subcategory?: string;
  address?: string;
  distance_m?: number;
  walking_distance_m?: number;
  walking_time_min?: number;
  data_source?: string;
  verification_status?: string;
  missing_items?: string[];
  missing_items_text?: string;
  notes?: string;
  supplement?: Record<string, any>;
  is_manual?: boolean;
};

export type PoiListResponse = {
  evaluation_id: number;
  total: number;
  counts: Record<string, number>;
  statistics?: Record<string, Record<string, number | string>>;
  items: PoiPublic[];
};

export type Poi = {
  id: number;
  name: string;
  category: string;
  type_code?: string;
  address?: string;
  longitude: number;
  latitude: number;
  distance_m?: number;
  source: string;
  confidence: number;
  needs_verification: boolean;
  is_manually_verified?: boolean;
  enrichment?: CompetitorEnrichment;
  survey_record_count?: number;
};

export type Score = {
  total_score: number;
  recommendation: string;
  dimensions: Record<string, number>;
  positive_evidence: string[];
  negative_evidence: string[];
  hard_risks: {message: string; level: string; code?: string}[];
  review_items: string[];
  completeness: number;
  confidence: number;
  model_version: string;
};
