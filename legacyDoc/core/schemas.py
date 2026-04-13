# core/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional

class ArgDetail(BaseModel):
    name: str = Field(description="Parameter name")
    type: str = Field(description="Data type (ex: int, std::string)")
    description: str = Field(description="What does this parameter do?")

class RaiseDetail(BaseModel):
    exception: str = Field(description="Exception Name (ex: std::invalid_argument)")
    condition: str = Field(description="The condition that causes this exception to be thrown")

class DocstringSchema(BaseModel):
    summary: str = Field(description="Short summary in imperative mood (max 1 line).")
    description: str = Field(description="Detailed explanation of the business logic.")
    args: Optional[List[ArgDetail]] = Field(default=[])
    returns: str = Field(description="Return type and description. Use 'None' if void.")
    raises: Optional[List[RaiseDetail]] = Field(default=[])