from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

class WellData(BaseModel):
    well_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plate_id: str
    well_position: str  # e.g., "A1"
    row: int
    column: int
    od_raw: float
    od_bg_subtracted: Optional[float] = None
    is_blank: bool = False
    strain: Optional[str] = None
    antibiotic: Optional[str] = None
    concentration: Optional[float] = None
    concentration_unit: Optional[str] = "ug/mL"
    media: Optional[str] = None
    replicate: Optional[int] = 1
    growth_call: Optional[bool] = None  # True for growth, False for no growth
    notes: Optional[str] = None
    extra_labels: Dict[str, str] = Field(default_factory=dict)

class PlateData(BaseModel):
    plate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    experiment_id: str
    plate_name: str
    plate_format: int = 96
    threshold: float = 0.010
    threshold_method: str = "fixed"
    background_method: str = "average_blanks"
    created_at: datetime = Field(default_factory=datetime.now)
    wells: List[WellData] = []

class ExperimentData(BaseModel):
    experiment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date: str
    person: str
    reader: Optional[str] = None
    incubation_time: Optional[float] = None
    inoculum_od: Optional[float] = None
    growth_phase: Optional[str] = None
    harvest_od: Optional[float] = None
    doubling_time: Optional[float] = None
    notes: Optional[str] = None
    extra_metadata_json: Optional[str] = None # JSON string

class MICResult(BaseModel):
    mic_result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plate_id: str
    group_id: str  # strain+antibiotic+media+replicate
    strain: str
    antibiotic: str
    media: str
    replicate: int
    mic_value: float
    mic_operator: str = "="  # "=", ">", "<", "<="
    mic_unit: str = "ug/mL"
    threshold_used: float
    lowest_tested_conc: float
    highest_tested_conc: float
    concentration_values_json: str  # list of concentrations tested
    num_points: int
    calculation_status: Optional[str] = "success"
    warning: Optional[str] = None
