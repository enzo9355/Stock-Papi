# -*- coding: utf-8 -*-
"""Dataclass definitions and canonical serializer for Regression Research Artifacts."""

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

REGRESSION_ARTIFACT_SCHEMA_VERSION = 1
REGRESSION_ARTIFACT_KIND = "absorb-regression-research-artifact"
MAX_REGRESSION_ARTIFACT_BYTES = 2_000_000

FORBIDDEN_WORDS = (
    "Probability",
    "\u52dd\u7387",  # 勝率
    "\u4e0a\u6f35\u6a5f\u7387",  # 上漲機率
    "\u4e0b\u8dcc\u6a5f\u7387",  # 下跌機率
    "\u6b63\u5f0f\u9810\u6e2c",  # 正式預測
    "\u8cb7\u9032\u8a0a\u865f",  # 買進訊號
    "\u8ce3\u51fa\u8a0a\u865f",  # 賣出訊號
)


@dataclass(frozen=True)
class RegressionIdentity:
    artifact_id: str
    market: str
    source_market_date: str
    applicable_trading_date: str
    generated_at: str
    source_manifest: str
    source_manifest_sha256: str
    input_dataset_object: str
    input_dataset_sha256: str
    input_dataset_content_sha256: str
    input_dataset_rows_sha256: str
    code_commit_sha: str
    generator_version: str
    content_sha256: str
    regression_spec_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "market": self.market,
            "source_market_date": self.source_market_date,
            "applicable_trading_date": self.applicable_trading_date,
            "generated_at": self.generated_at,
            "source_manifest": self.source_manifest,
            "source_manifest_sha256": self.source_manifest_sha256,
            "input_dataset_object": self.input_dataset_object,
            "input_dataset_sha256": self.input_dataset_sha256,
            "input_dataset_content_sha256": self.input_dataset_content_sha256,
            "input_dataset_rows_sha256": self.input_dataset_rows_sha256,
            "code_commit_sha": self.code_commit_sha,
            "generator_version": self.generator_version,
            "content_sha256": self.content_sha256,
            "regression_spec_version": self.regression_spec_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegressionIdentity":
        return cls(
            artifact_id=data["artifact_id"],
            market=data["market"],
            source_market_date=data["source_market_date"],
            applicable_trading_date=data["applicable_trading_date"],
            generated_at=data["generated_at"],
            source_manifest=data["source_manifest"],
            source_manifest_sha256=data["source_manifest_sha256"],
            input_dataset_object=data["input_dataset_object"],
            input_dataset_sha256=data["input_dataset_sha256"],
            input_dataset_content_sha256=data["input_dataset_content_sha256"],
            input_dataset_rows_sha256=data["input_dataset_rows_sha256"],
            code_commit_sha=data["code_commit_sha"],
            generator_version=data["generator_version"],
            content_sha256=data.get("content_sha256", ""),
            regression_spec_version=data.get("regression_spec_version", "1.0"),
        )


@dataclass(frozen=True)
class RegressionSpec:
    analysis_scope: str
    entity_type: str
    universe_definition: str
    observation_unit: str
    model_family: str
    dependent_variable: str
    dependent_variable_definition: str
    independent_variables: list[str]
    intercept: bool
    frequency: str
    first_feature_session: str
    last_feature_session: str
    first_label_end_session: str
    last_label_end_session: str
    label_horizon_sessions: int
    sample_count: int
    missing_value_policy: str
    standardization_policy: str
    outlier_policy: str
    covariance_estimator: str
    hac_max_lags: int
    confidence_level: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_scope": self.analysis_scope,
            "entity_type": self.entity_type,
            "universe_definition": self.universe_definition,
            "observation_unit": self.observation_unit,
            "model_family": self.model_family,
            "dependent_variable": self.dependent_variable,
            "dependent_variable_definition": self.dependent_variable_definition,
            "independent_variables": list(self.independent_variables),
            "intercept": self.intercept,
            "frequency": self.frequency,
            "first_feature_session": self.first_feature_session,
            "last_feature_session": self.last_feature_session,
            "first_label_end_session": self.first_label_end_session,
            "last_label_end_session": self.last_label_end_session,
            "label_horizon_sessions": self.label_horizon_sessions,
            "sample_count": self.sample_count,
            "missing_value_policy": self.missing_value_policy,
            "standardization_policy": self.standardization_policy,
            "outlier_policy": self.outlier_policy,
            "covariance_estimator": self.covariance_estimator,
            "hac_max_lags": self.hac_max_lags,
            "confidence_level": self.confidence_level,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegressionSpec":
        return cls(
            analysis_scope=data["analysis_scope"],
            entity_type=data["entity_type"],
            universe_definition=data["universe_definition"],
            observation_unit=data["observation_unit"],
            model_family=data["model_family"],
            dependent_variable=data["dependent_variable"],
            dependent_variable_definition=data["dependent_variable_definition"],
            independent_variables=list(data["independent_variables"]),
            intercept=data["intercept"],
            frequency=data["frequency"],
            first_feature_session=data["first_feature_session"],
            last_feature_session=data["last_feature_session"],
            first_label_end_session=data["first_label_end_session"],
            last_label_end_session=data["last_label_end_session"],
            label_horizon_sessions=data["label_horizon_sessions"],
            sample_count=data["sample_count"],
            missing_value_policy=data["missing_value_policy"],
            standardization_policy=data["standardization_policy"],
            outlier_policy=data["outlier_policy"],
            covariance_estimator=data["covariance_estimator"],
            hac_max_lags=data["hac_max_lags"],
            confidence_level=data["confidence_level"],
        )


@dataclass(frozen=True)
class RegressionResultItem:
    factor_name: str
    display_label: str
    coefficient: float
    standard_error: float
    t_statistic: float
    p_value: float
    confidence_interval_low: float
    confidence_interval_high: float
    direction: str
    economic_magnitude: str
    display_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_name": self.factor_name,
            "display_label": self.display_label,
            "coefficient": self.coefficient,
            "standard_error": self.standard_error,
            "t_statistic": self.t_statistic,
            "p_value": self.p_value,
            "confidence_interval_low": self.confidence_interval_low,
            "confidence_interval_high": self.confidence_interval_high,
            "direction": self.direction,
            "economic_magnitude": self.economic_magnitude,
            "display_status": self.display_status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegressionResultItem":
        coef = data["coefficient"]
        low = data["confidence_interval_low"]
        high = data["confidence_interval_high"]
        se = data["standard_error"]
        if not (isinstance(coef, (int, float)) and isinstance(low, (int, float)) and isinstance(high, (int, float))):
            raise TypeError("Coefficient and CI bounds must be numbers")
        if isinstance(coef, bool) or isinstance(low, bool) or isinstance(high, bool):
            raise TypeError("Bools not allowed as floats")
        if low > coef or coef > high:
            raise ValueError(f"CI bounds invalid: low={low}, coef={coef}, high={high}")
        if se < 0:
            raise ValueError(f"Standard error must be non-negative, got {se}")
        return cls(
            factor_name=data["factor_name"],
            display_label=data["display_label"],
            coefficient=float(coef),
            standard_error=float(se),
            t_statistic=float(data["t_statistic"]),
            p_value=float(data["p_value"]),
            confidence_interval_low=float(low),
            confidence_interval_high=float(high),
            direction=data["direction"],
            economic_magnitude=data["economic_magnitude"],
            display_status=data["display_status"],
        )


@dataclass(frozen=True)
class RegressionFitStatistics:
    r_squared: float
    adjusted_r_squared: float
    residual_standard_error: float
    degrees_of_freedom: int
    f_statistic: float
    f_p_value: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "r_squared": self.r_squared,
            "adjusted_r_squared": self.adjusted_r_squared,
            "residual_standard_error": self.residual_standard_error,
            "degrees_of_freedom": self.degrees_of_freedom,
            "f_statistic": self.f_statistic,
            "f_p_value": self.f_p_value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegressionFitStatistics":
        r2 = data["r_squared"]
        adj_r2 = data["adjusted_r_squared"]
        df = data["degrees_of_freedom"]
        if not (0 <= r2 <= 1):
            raise ValueError(f"r_squared must be between 0 and 1, got {r2}")
        if df <= 0:
            raise ValueError(f"degrees_of_freedom must be > 0, got {df}")
        return cls(
            r_squared=float(r2),
            adjusted_r_squared=float(adj_r2),
            residual_standard_error=float(data["residual_standard_error"]),
            degrees_of_freedom=int(df),
            f_statistic=float(data["f_statistic"]),
            f_p_value=float(data["f_p_value"]),
        )


@dataclass(frozen=True)
class RegressionDiagnostics:
    multicollinearity: dict[str, Any]
    heteroskedasticity: dict[str, Any]
    autocorrelation: dict[str, Any]
    residual_normality: dict[str, Any]
    data_quality: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "multicollinearity": dict(self.multicollinearity),
            "heteroskedasticity": dict(self.heteroskedasticity),
            "autocorrelation": dict(self.autocorrelation),
            "residual_normality": dict(self.residual_normality),
            "data_quality": dict(self.data_quality),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegressionDiagnostics":
        return cls(
            multicollinearity=dict(data["multicollinearity"]),
            heteroskedasticity=dict(data["heteroskedasticity"]),
            autocorrelation=dict(data["autocorrelation"]),
            residual_normality=dict(data["residual_normality"]),
            data_quality=dict(data["data_quality"]),
            warnings=list(data.get("warnings", [])),
        )


@dataclass(frozen=True)
class RegressionPresentation:
    headline: str
    summary: str
    key_exposures: list[str]
    limitations: str
    disclosure: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "summary": self.summary,
            "key_exposures": list(self.key_exposures),
            "limitations": self.limitations,
            "disclosure": self.disclosure,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegressionPresentation":
        pres = cls(
            headline=data["headline"],
            summary=data["summary"],
            key_exposures=list(data["key_exposures"]),
            limitations=data["limitations"],
            disclosure=data["disclosure"],
        )
        body_text = f"{pres.headline} {pres.summary} {' '.join(pres.key_exposures)} {pres.limitations}"
        for word in FORBIDDEN_WORDS:
            if word in body_text:
                raise ValueError(f"Forbidden word '{word}' found in presentation")
        return pres


@dataclass(frozen=True)
class RegressionResearchArtifact:
    schema_version: int
    kind: str
    identity: RegressionIdentity
    regression_spec: RegressionSpec
    results: list[RegressionResultItem]
    fit_statistics: RegressionFitStatistics
    diagnostics: RegressionDiagnostics
    presentation: RegressionPresentation

    def to_document(self) -> dict[str, Any]:
        doc = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "identity": self.identity.to_dict(),
            "regression_spec": self.regression_spec.to_dict(),
            "results": [r.to_dict() for r in self.results],
            "fit_statistics": self.fit_statistics.to_dict(),
            "diagnostics": self.diagnostics.to_dict(),
            "presentation": self.presentation.to_dict(),
        }
        return doc

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "RegressionResearchArtifact":
        if not isinstance(document, dict) or not document:
            raise ValueError("Document must be a non-empty dict")
        if document.get("schema_version") != REGRESSION_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(f"Invalid schema_version: {document.get('schema_version')}")
        if document.get("kind") != REGRESSION_ARTIFACT_KIND:
            raise ValueError(f"Invalid kind: {document.get('kind')}")

        identity = RegressionIdentity.from_dict(document["identity"])
        spec = RegressionSpec.from_dict(document["regression_spec"])
        results = [RegressionResultItem.from_dict(r) for r in document["results"]]
        fit_stats = RegressionFitStatistics.from_dict(document["fit_statistics"])
        diagnostics = RegressionDiagnostics.from_dict(document["diagnostics"])
        presentation = RegressionPresentation.from_dict(document["presentation"])

        artifact = cls(
            schema_version=int(document["schema_version"]),
            kind=str(document["kind"]),
            identity=identity,
            regression_spec=spec,
            results=results,
            fit_statistics=fit_stats,
            diagnostics=diagnostics,
            presentation=presentation,
        )
        return artifact


def serialize_regression_artifact(document: dict[str, Any]) -> bytes:
    """Serialize artifact dict into canonical UTF-8 JSON bytes."""
    serialized = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(serialized) > MAX_REGRESSION_ARTIFACT_BYTES:
        raise ValueError(f"Serialized regression artifact exceeds size limit: {len(serialized)} > {MAX_REGRESSION_ARTIFACT_BYTES}")
    return serialized


def compute_regression_artifact_content_sha256(document: dict[str, Any]) -> str:
    """Compute semantic content SHA-256 over canonical bytes with content_sha256=''."""
    doc_copy = json.loads(json.dumps(document))
    if "identity" in doc_copy:
        doc_copy["identity"]["content_sha256"] = ""
    canonical_bytes = serialize_regression_artifact(doc_copy)
    return hashlib.sha256(canonical_bytes).hexdigest()
