from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class AgentRunRequest(BaseModel):
    rtl_code: str
    job_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    simulation_log: Optional[str] = None
    testbench_code: Optional[str] = None


class PredictionRequest(BaseModel):
    rtl_code: str
    job_id: Optional[str] = None
    module_type: Optional[str] = None


class ChatStreamRequest(BaseModel):
    system: str
    prompt: str


class SimulateRequest(BaseModel):
    rtl_code: str
    testbench_code: str
    job_id: Optional[str] = ""


class ConfirmBugRequest(BaseModel):
    notes: Optional[str] = ""
