from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ArgumentRule(BaseModel):
    """Constraints applied to a single tool argument."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    data_type: Literal["string", "int", "float", "bool", "dict", "list"]
    required: bool = True
    max_length: Optional[int] = Field(default=None, ge=1)
    regex_pattern: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[Tuple[str, ...]] = None


class ToolPolicy(BaseModel):
    """Policy rules governing a specific tool."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_name: str = Field(min_length=1, max_length=64)
    allowed: bool = True
    requires_approval: bool = False
    argument_rules: Tuple[ArgumentRule, ...] = Field(default_factory=tuple)


class QuotaConfig(BaseModel):
    """Request quotas enforced by the gateway."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_requests_per_window: int = Field(ge=1, default=100)
    window_seconds: int = Field(ge=1, default=3600)


class SecurityPolicy(BaseModel):
    """Immutable, frozen policy defining the agent security boundary."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: str = Field(min_length=1, max_length=64)
    version: int = Field(ge=1)
    description: str = Field(max_length=256)
    is_revoked: bool = False
    quota: QuotaConfig = Field(default_factory=QuotaConfig)
    allowed_tools: Tuple[ToolPolicy, ...] = Field(default_factory=tuple)

    @field_validator("allowed_tools")
    @classmethod
    def unique_tool_names(cls, tools: Tuple[ToolPolicy, ...]) -> Tuple[ToolPolicy, ...]:
        names = [t.tool_name for t in tools]
        if len(names) != len(set(names)):
            raise ValueError("duplicate_tool_names_in_policy")
        return tools


class PolicyViolation(BaseModel):
    """Standardized machine-readable policy violation."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    tool_name: str
    message: str
    field_path: Tuple[str, ...] = Field(default_factory=tuple)
    severity: Literal["error", "warning"] = "error"


class PolicyEvaluationResult(BaseModel):
    """Deterministic evaluation outcome for an action request."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: str
    policy_version: int
    authorized: bool
    requires_approval: bool
    violations: Tuple[PolicyViolation, ...] = Field(default_factory=tuple)
    action_fingerprint: str
