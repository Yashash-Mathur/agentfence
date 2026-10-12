import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field

from gateway.policy.schema import (
    ArgumentRule,
    PolicyEvaluationResult,
    PolicyViolation,
    SecurityPolicy,
    ToolPolicy,
)


def compute_action_fingerprint(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Computes a deterministic SHA-256 hash of tool invocation parameters."""
    canonical = json.dumps(
        {"tool_name": tool_name, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PolicyEngine:
    """
    Deterministic Policy Evaluation Engine.
    Evaluates action requests strictly against an immutable SecurityPolicy.
    Purity Guarantee: Given the same policy, tool_name, and arguments,
    it produces identical results with no external clock or I/O dependencies.
    """

    @staticmethod
    def evaluate(
        policy: SecurityPolicy,
        tool_name: str,
        arguments: Dict[str, Any],
        is_revoked_override: Optional[bool] = None,
    ) -> PolicyEvaluationResult:
        violations: List[PolicyViolation] = []
        action_fp = compute_action_fingerprint(tool_name, arguments)

        # 1. Policy Revocation Check
        is_revoked = is_revoked_override if is_revoked_override is not None else policy.is_revoked
        if is_revoked:
            violations.append(
                PolicyViolation(
                    code="POLICY_REVOKED",
                    tool_name=tool_name,
                    message=f"Policy '{policy.policy_id}' version {policy.version} is revoked.",
                    field_path=("policy", "is_revoked"),
                )
            )
            return PolicyEvaluationResult(
                policy_id=policy.policy_id,
                policy_version=policy.version,
                authorized=False,
                requires_approval=False,
                violations=tuple(violations),
                action_fingerprint=action_fp,
            )

        # 2. Tool Registration & Whitelist Check (Default Deny)
        tool_rule: Optional[ToolPolicy] = None
        for t in policy.allowed_tools:
            if t.tool_name == tool_name:
                tool_rule = t
                break

        if tool_rule is None:
            violations.append(
                PolicyViolation(
                    code="TOOL_NOT_REGISTERED",
                    tool_name=tool_name,
                    message=f"Tool '{tool_name}' is not registered in the active policy allowlist.",
                    field_path=("allowed_tools",),
                )
            )
            return PolicyEvaluationResult(
                policy_id=policy.policy_id,
                policy_version=policy.version,
                authorized=False,
                requires_approval=False,
                violations=tuple(violations),
                action_fingerprint=action_fp,
            )

        if not tool_rule.allowed:
            violations.append(
                PolicyViolation(
                    code="TOOL_EXPLICITLY_DISALLOWED",
                    tool_name=tool_name,
                    message=f"Tool '{tool_name}' is registered but explicitly disallowed.",
                    field_path=("allowed_tools", tool_name, "allowed"),
                )
            )

        # 3. Argument Validation
        rules_by_arg = {r.name: r for r in tool_rule.argument_rules}

        # Check required arguments
        for arg_name, rule in rules_by_arg.items():
            if rule.required and arg_name not in arguments:
                violations.append(
                    PolicyViolation(
                        code="ARGUMENT_MISSING",
                        tool_name=tool_name,
                        message=f"Required argument '{arg_name}' was not provided.",
                        field_path=("arguments", arg_name),
                    )
                )

        # Validate provided arguments
        for arg_name, arg_val in arguments.items():
            if arg_name not in rules_by_arg:
                # Extra argument forbidden
                violations.append(
                    PolicyViolation(
                        code="UNEXPECTED_ARGUMENT",
                        tool_name=tool_name,
                        message=f"Argument '{arg_name}' is not recognized for tool '{tool_name}'.",
                        field_path=("arguments", arg_name),
                    )
                )
                continue

            rule = rules_by_arg[arg_name]

            # Type check
            type_valid = True
            if rule.data_type == "string" and not isinstance(arg_val, str):
                type_valid = False
            elif rule.data_type == "int" and not (isinstance(arg_val, int) and not isinstance(arg_val, bool)):
                type_valid = False
            elif rule.data_type == "float" and not (isinstance(arg_val, (int, float)) and not isinstance(arg_val, bool)):
                type_valid = False
            elif rule.data_type == "bool" and not isinstance(arg_val, bool):
                type_valid = False
            elif rule.data_type == "dict" and not isinstance(arg_val, dict):
                type_valid = False
            elif rule.data_type == "list" and not isinstance(arg_val, list):
                type_valid = False

            if not type_valid:
                violations.append(
                    PolicyViolation(
                        code="ARGUMENT_TYPE_MISMATCH",
                        tool_name=tool_name,
                        message=f"Argument '{arg_name}' expected type '{rule.data_type}', received '{type(arg_val).__name__}'.",
                        field_path=("arguments", arg_name),
                    )
                )
                continue

            # String constraints
            if isinstance(arg_val, str):
                if rule.max_length is not None and len(arg_val) > rule.max_length:
                    violations.append(
                        PolicyViolation(
                            code="ARGUMENT_LENGTH_EXCEEDED",
                            tool_name=tool_name,
                            message=f"Argument '{arg_name}' length ({len(arg_val)}) exceeds limit {rule.max_length}.",
                            field_path=("arguments", arg_name),
                        )
                    )
                if rule.regex_pattern is not None:
                    if not re.fullmatch(rule.regex_pattern, arg_val):
                        violations.append(
                            PolicyViolation(
                                code="ARGUMENT_PATTERN_MISMATCH",
                                tool_name=tool_name,
                                message=f"Argument '{arg_name}' does not match pattern '{rule.regex_pattern}'.",
                                field_path=("arguments", arg_name),
                            )
                        )
                if rule.allowed_values is not None and arg_val not in rule.allowed_values:
                    violations.append(
                        PolicyViolation(
                            code="ARGUMENT_VALUE_NOT_ALLOWED",
                            tool_name=tool_name,
                            message=f"Argument '{arg_name}' has value '{arg_val}', expected one of {rule.allowed_values}.",
                            field_path=("arguments", arg_name),
                        )
                    )

            # Numeric constraints
            if isinstance(arg_val, (int, float)) and not isinstance(arg_val, bool):
                if rule.min_value is not None and arg_val < rule.min_value:
                    violations.append(
                        PolicyViolation(
                            code="ARGUMENT_VALUE_TOO_LOW",
                            tool_name=tool_name,
                            message=f"Argument '{arg_name}' value {arg_val} < min_value {rule.min_value}.",
                            field_path=("arguments", arg_name),
                        )
                    )
                if rule.max_value is not None and arg_val > rule.max_value:
                    violations.append(
                        PolicyViolation(
                            code="ARGUMENT_VALUE_TOO_HIGH",
                            tool_name=tool_name,
                            message=f"Argument '{arg_name}' value {arg_val} > max_value {rule.max_value}.",
                            field_path=("arguments", arg_name),
                        )
                    )

        # Sorted deterministic violations
        sorted_violations = tuple(sorted(violations, key=lambda v: (v.field_path, v.code)))
        authorized = len(sorted_violations) == 0

        return PolicyEvaluationResult(
            policy_id=policy.policy_id,
            policy_version=policy.version,
            authorized=authorized,
            requires_approval=tool_rule.requires_approval if authorized else False,
            violations=sorted_violations,
            action_fingerprint=action_fp,
        )
