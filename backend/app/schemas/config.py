from pydantic import BaseModel


class CameraIn(BaseModel):
    name: str
    source_type: str  # mp4 | webcam | rtsp
    uri: str
    loop: bool = True


class CameraOut(CameraIn):
    id: str
    status: str
    consecutive_failures: int
    active: bool

    class Config:
        from_attributes = True


class ZoneIn(BaseModel):
    camera_id: str
    name: str
    polygon: list[list[float]]  # [[x,y], ...] normalized 0-1
    restricted: bool = False
    loitering_threshold_s: int = 30
    after_hours_monitored: bool = True


class ZoneOut(BaseModel):
    id: str
    camera_id: str
    name: str
    polygon: list[list[float]]
    restricted: bool
    loitering_threshold_s: int
    after_hours_monitored: bool

    class Config:
        from_attributes = True


class ScheduleIn(BaseModel):
    scope: str  # camera | zone
    scope_id: str
    business_hours: dict[str, list[list[str]]]  # {"mon": [["08:00","18:00"]], ...}


class ScheduleOut(ScheduleIn):
    id: str

    class Config:
        from_attributes = True


class SOPIn(BaseModel):
    incident_type: str
    title: str
    steps_text: str


class SOPOut(SOPIn):
    id: str

    class Config:
        from_attributes = True
