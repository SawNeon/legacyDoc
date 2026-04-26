from pydantic import BaseModel, Field
from typing import List, Optional

class ArgDetail(BaseModel):
    name: str = Field(description="The name of the parameter")
    type: str = Field(description="The technical data type (e.g., const int64_t, Bitu)")

class FunctionDetail(BaseModel):
    name: str = Field(description="The name of the function")
    kind: str = Field(default="function", description="The type of the entry, always 'function'")
    return_type: str = Field(description="The return data type (e.g., void, int64_t, bool)")
    args: List[ArgDetail] = Field(default=[], description="A list of the function's arguments")
    summary: str = Field(description="A one-line summary in Brazilian Portuguese")
    description: str = Field(description="A first-person explanation (Situation, Action, Impact) in Brazilian Portuguese")
    raises: List[str] = Field(default=[], description="A list of exceptions thrown by the function (strings)")

class FileDocumentation(BaseModel):
    functions: List[FunctionDetail] = Field(description="An array containing all functions extracted from the file")