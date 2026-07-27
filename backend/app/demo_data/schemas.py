from __future__ import annotations

from pydantic import BaseModel, Field


class DemoDataGenerateRequest(BaseModel):
    include: list[str] = Field(
        default_factory=lambda: ["competitor", "supporting", "rent"],
        description="需要生成演示数据的类型：competitor、supporting、rent",
    )
    max_competitors: int = Field(default=8, ge=1, le=30)
    max_supporting: int = Field(default=12, ge=1, le=50)
    rent_samples: int = Field(default=5, ge=1, le=20)


class DemoDataGenerateResponse(BaseModel):
    success: bool = True
    project_id: str
    generated: dict[str, int]
    updated: dict[str, int]
    message: str
    warning: str

