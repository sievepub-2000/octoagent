from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ToolPermissionScope = Literal["sandbox", "directory", "system"]


class ToolGroupConfig(BaseModel):
    """Config section for a tool group"""

    name: str = Field(..., description="Unique name for the tool group")
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ToolConfig(BaseModel):
    """Config section for a tool"""

    name: str = Field(..., description="Unique name for the tool")
    group: str = Field(..., description="Group name for the tool")
    use: str = Field(
        ...,
        description="Variable name of the tool provider(e.g. src.tools.sandbox.tools:bash_tool)",
    )
    permission_scope: ToolPermissionScope = Field(
        default="sandbox",
        alias="permissionScope",
        description="Tool permission scope: sandbox, directory, or system. Defaults to sandbox.",
    )
    model_config = ConfigDict(extra="allow")
