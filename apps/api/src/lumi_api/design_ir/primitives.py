from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    field_validator,
    model_validator,
)


class DesignModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class RgbaColor(DesignModel):
    color_space: Literal["srgb"] = "srgb"
    r: FiniteFloat = Field(ge=0, le=1)
    g: FiniteFloat = Field(ge=0, le=1)
    b: FiniteFloat = Field(ge=0, le=1)
    a: FiniteFloat = Field(default=1, ge=0, le=1)


class Point2D(DesignModel):
    x: FiniteFloat = 0
    y: FiniteFloat = 0


class Size2D(DesignModel):
    width: FiniteFloat = Field(gt=0, le=1_000_000)
    height: FiniteFloat = Field(gt=0, le=1_000_000)


class Transform2D(DesignModel):
    x: FiniteFloat = 0
    y: FiniteFloat = 0
    rotation_deg: FiniteFloat = 0
    scale_x: FiniteFloat = 1
    scale_y: FiniteFloat = 1
    skew_x_deg: FiniteFloat = 0
    skew_y_deg: FiniteFloat = 0

    @field_validator("scale_x", "scale_y")
    @classmethod
    def reject_zero_scale(cls, value: float) -> float:
        if value == 0:
            raise ValueError("scale must not be zero")
        return value


class NormalizedRect(DesignModel):
    x: FiniteFloat = Field(ge=0, le=1)
    y: FiniteFloat = Field(ge=0, le=1)
    width: FiniteFloat = Field(gt=0, le=1)
    height: FiniteFloat = Field(gt=0, le=1)

    @model_validator(mode="after")
    def remain_inside_unit_square(self) -> NormalizedRect:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("normalized crop must stay inside [0,1] bounds")
        return self


class GradientStop(DesignModel):
    position: FiniteFloat = Field(ge=0, le=1)
    color: RgbaColor


class SolidPaint(DesignModel):
    kind: Literal["solid"] = "solid"
    color: RgbaColor
    token_ref: str | None = Field(default=None, max_length=200)


class LinearGradientPaint(DesignModel):
    kind: Literal["linear_gradient"] = "linear_gradient"
    angle_deg: FiniteFloat = 0
    stops: tuple[GradientStop, ...] = Field(min_length=2, max_length=64)
    token_ref: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def require_sorted_stops(self) -> LinearGradientPaint:
        positions = [stop.position for stop in self.stops]
        if positions != sorted(positions):
            raise ValueError("gradient stops must be ordered by position")
        return self


Paint = Annotated[SolidPaint | LinearGradientPaint, Field(discriminator="kind")]


class StrokeStyle(DesignModel):
    paint: Paint
    width: FiniteFloat = Field(ge=0, le=10_000)
    alignment: Literal["inside", "center", "outside"] = "center"
    line_cap: Literal["butt", "round", "square"] = "butt"
    line_join: Literal["miter", "round", "bevel"] = "miter"


class ShadowEffect(DesignModel):
    offset: Point2D = Point2D()
    blur: FiniteFloat = Field(default=0, ge=0, le=10_000)
    spread: FiniteFloat = Field(default=0, ge=-10_000, le=10_000)
    color: RgbaColor = RgbaColor(r=0, g=0, b=0, a=0.25)


class TextStyle(DesignModel):
    font_family: str = Field(min_length=1, max_length=200)
    font_asset_id: UUID | None = None
    font_size: FiniteFloat = Field(gt=0, le=10_000)
    font_weight: int = Field(default=400, ge=100, le=900, multiple_of=100)
    italic: bool = False
    line_height: FiniteFloat = Field(default=1.2, gt=0, le=20)
    letter_spacing: FiniteFloat = Field(default=0, ge=-1_000, le=10_000)
    align: Literal["left", "center", "right", "justify"] = "left"
    vertical_align: Literal["top", "middle", "bottom"] = "top"
    color: RgbaColor = RgbaColor(r=0, g=0, b=0, a=1)
