from pydantic import BaseModel, Field
from typing import List, Optional


class ArgDetail(BaseModel):
    name: str = Field(description="The name of the parameter")
    type: str = Field(description="The technical data type")
    description: Optional[str] = Field(
        default=None,
        description="A short explanation of the parameter"
    )


class FunctionDetail(BaseModel):
    name: str = Field(description="The name of the function")
    kind: str = Field(default="function")
    signature: str = Field(description="The original function signature")
    return_type: str = Field(description="The return data type")
    return_description: Optional[str] = Field(
        default=None,
        description="Explanation of what the function returns"
    )
    args: List[ArgDetail] = Field(default_factory=list)
    summary: str = Field(description="A one-line summary in Brazilian Portuguese")
    description: str = Field(description="A first-person explanation in Brazilian Portuguese")
    raises: List[str] = Field(default_factory=list)


class FileDocumentation(BaseModel):
    functions: List[FunctionDetail] = Field(default_factory=list)