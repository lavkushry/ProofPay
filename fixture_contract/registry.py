"""Load reviewed fixture facts; validate schema, paths and every content digest."""

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Family = Literal["responsive_css", "api_endpoint", "keyboard_accessibility"]
ROOT = Path(__file__).parent
FAMILY_TEMPLATES = {
    "responsive_css": ("viewport_no_horizontal_overflow", "cart_total_unchanged", "keyboard_checkout_reachable"),
    "api_endpoint": ("api_status", "api_schema", "api_total_matches_fixture"),
    "keyboard_accessibility": ("keyboard_checkout_reachable", "keyboard_activation", "accessible_control_name"),
}


class CatalogIntegrityError(ValueError):
    pass


def decode_json(value):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise CatalogIntegrityError("Duplicate JSON field")
            result[key] = item
        return result
    def non_finite(_):
        raise CatalogIntegrityError("Non-finite JSON value")
    return json.loads(value, object_pairs_hook=unique, parse_constant=non_finite)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class FixtureFacts(ContractModel):
    supported_widths: list[Literal[320]] = Field(min_length=1, max_length=1)
    target_ref: Literal["checkout"]
    target_dom_id: Literal["checkout"]
    baseline_ref: Literal["fixture_cart_v1"]
    total_cents: int = Field(ge=0, le=100000000)
    currency: Literal["USD"]
    endpoint_ref: Literal["cart_total"]
    endpoint_path: Literal["/api/cart-total"]
    schema_ref: Literal["cart_total_response_v1"]
    control_ref: Literal["checkout_pay"]
    control_dom_id: Literal["checkout_pay"]
    accessible_name_ref: Literal["checkout_pay_name_v1"]
    accessible_name: str = Field(min_length=1, max_length=100)


class Template(ContractModel):
    template_type: str
    description: str = Field(min_length=1, max_length=300)
    params: dict


class FamilyDefinition(ContractModel):
    family: Family
    name: str = Field(min_length=1, max_length=100)
    templates: list[Template] = Field(min_length=3, max_length=3)


class Artifact(ContractModel):
    artifact_ref: str = Field(pattern=r"^checkout_[a-z0-9_]{1,80}$")
    family: Family
    label: str = Field(min_length=1, max_length=150)
    relative_path: str
    file: str
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def fixed_paths(self):
        extension = "json" if self.family == "api_endpoint" else "html"
        if self.relative_path != f"/versions/{self.artifact_ref}" or self.file != f"assets/{self.artifact_ref}.{extension}":
            raise ValueError("Artifact paths must resolve inside the reviewed fixture")
        return self


class FixtureContract(ContractModel):
    schema_version: Literal["fixture-manifest-v1"]
    fixture_ref: Literal["checkout_fixture"]
    version: int = Field(ge=1)
    facts: FixtureFacts
    families: list[FamilyDefinition] = Field(min_length=3, max_length=3)
    artifacts: list[Artifact] = Field(min_length=6, max_length=100)

    @property
    def digest(self):
        return hashlib.sha256(canonical_bytes(self.model_dump(mode="json"))).hexdigest()

    @model_validator(mode="after")
    def reviewed_contracts(self):
        if {f.family for f in self.families} != set(FAMILY_TEMPLATES):
            raise ValueError("All three fixture families are required")
        parameters = {
            "viewport_no_horizontal_overflow": {"width": self.facts.supported_widths[0], "target_ref": self.facts.target_ref},
            "cart_total_unchanged": {"baseline_ref": self.facts.baseline_ref},
            "keyboard_checkout_reachable": {"control_ref": self.facts.control_ref},
            "api_status": {"target_ref": self.facts.endpoint_ref, "expected_status": 200},
            "api_schema": {"target_ref": self.facts.endpoint_ref, "schema": self.facts.schema_ref},
            "api_total_matches_fixture": {"target_ref": self.facts.endpoint_ref, "baseline_ref": self.facts.baseline_ref},
            "keyboard_activation": {"control_ref": self.facts.control_ref, "key": "Enter"},
            "accessible_control_name": {"control_ref": self.facts.control_ref, "name": self.facts.accessible_name_ref},
        }
        for family in self.families:
            if tuple(t.template_type for t in family.templates) != FAMILY_TEMPLATES[family.family]:
                raise ValueError("Unsupported family template contract")
            if any(canonical_bytes(t.params) != canonical_bytes(parameters[t.template_type]) for t in family.templates):
                raise ValueError("Template parameters must resolve to trusted fixture facts")
        if len({a.artifact_ref for a in self.artifacts}) != len(self.artifacts):
            raise ValueError("Artifact references must be unique")
        if any(sum(a.family == family for a in self.artifacts) < 2 for family in FAMILY_TEMPLATES):
            raise ValueError("Each family needs broken and corrected artifacts")
        return self

    def family(self, family):
        return next(item for item in self.families if item.family == family)

    def artifact(self, reference):
        return next((item for item in self.artifacts if item.artifact_ref == reference), None)


def load_contract(directory=ROOT):
    try:
        contract = FixtureContract.model_validate(decode_json((directory / "manifest.json").read_bytes()))
        for artifact in contract.artifacts:
            path = directory / artifact.file
            if not path.resolve().is_relative_to(directory.resolve()):
                raise CatalogIntegrityError("Artifact escaped the fixture package")
            content = path.read_bytes()
            if len(content) > 65536 or hashlib.sha256(content).hexdigest() != artifact.digest:
                raise CatalogIntegrityError("Artifact bytes do not match their approved digest")
            if artifact.family == "api_endpoint":
                response = decode_json(content)
                if set(response) != {"status_code", "body"} or type(response["status_code"]) is not int or not 100 <= response["status_code"] <= 599 or not isinstance(response["body"], dict):
                    raise CatalogIntegrityError("Invalid fixture response envelope")
        return contract
    except (OSError, ValueError, TypeError) as error:
        raise CatalogIntegrityError("Trusted fixture catalog is invalid") from error


def artifact_bytes(contract, reference, directory=ROOT):
    artifact = contract.artifact(reference)
    if artifact is None:
        raise CatalogIntegrityError("Unknown artifact reference")
    content = (directory / artifact.file).read_bytes()
    if hashlib.sha256(content).hexdigest() != artifact.digest:
        raise CatalogIntegrityError("Artifact content changed after catalog loading")
    return content
