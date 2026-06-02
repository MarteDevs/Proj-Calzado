from pydantic import BaseModel, Field, HttpUrl
from typing import Optional


class FootMeasurementRequest(BaseModel):
    image_url: HttpUrl
    user_id: str = Field(..., min_length=1)
    height_cm: Optional[float] = Field(None, gt=50, lt=250, description="Estatura en centímetros")
    weight_kg: Optional[float] = Field(None, gt=10, lt=300, description="Peso en kilogramos")
    wearing_socks: Optional[bool] = Field(False, description="Indica si el usuario tiene puestos calcetines en la foto")


class FootMeasurementResponse(BaseModel):
    shoe_size: str
    brand_advice: str
    confidence: float
