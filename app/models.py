from dataclasses import dataclass
from enum import Enum, IntEnum

class SemanticVersionPrecision(Enum):
    PATCH = "Patch"
    MINOR = "Minor"
    MAJOR = "Major"

class BumpSize(IntEnum):
    DIGEST = 0
    PATCH = 1
    MINOR = 2
    MAJOR = 3


class SemanticVersionSize(Enum):
    EQUAL = "Equal"
    PATCH = "Patch"
    MINOR = "Minor"
    MAJOR = "Major"
    DOWNGRADE = "Downgrade"
    PRECISION_MISMATCH = "PrecisionMismatch"

@dataclass(frozen=True)
class DockerComposeTarget:
    file_path: str
    service_key: str
    line: int
    current_image_string: str
    bump: BumpSize
    skip: bool

    def __str__(self) -> str:
        return f"DockerCompose:{self.file_path}:{self.service_key}"


@dataclass(frozen=True)
class SemanticVersion:
    major: int
    minor: int | None = None
    patch: int | None = None
    version_prefix: str | None = None

    def __str__(self) -> str:
        parts = []
        if self.version_prefix:
            parts.append(self.version_prefix)
        parts.append(str(self.major))
        if self.minor is not None:
            parts.append(str(self.minor))
            if self.patch is not None:
                parts.append(str(self.patch))
        return ".".join(parts)

    @property
    def precision(self) -> SemanticVersionPrecision:
        if self.minor is not None:
            if self.patch is not None:
                return SemanticVersionPrecision.PATCH
            return SemanticVersionPrecision.MINOR
        return SemanticVersionPrecision.MAJOR

    @staticmethod
    def compare(from_: "SemanticVersion", to: "SemanticVersion") -> SemanticVersionSize:
        if from_.precision != to.precision:
            return SemanticVersionSize.PRECISION_MISMATCH
        if to.major < from_.major:
            return SemanticVersionSize.DOWNGRADE
        if to.major > from_.major:
            return SemanticVersionSize.MAJOR
        if to.minor is None:
            return SemanticVersionSize.EQUAL
        if from_.minor is None or to.minor < from_.minor:
            return SemanticVersionSize.DOWNGRADE
        if to.minor > from_.minor:
            return SemanticVersionSize.MINOR
        if to.patch is None:
            return SemanticVersionSize.EQUAL
        if from_.patch is None or to.patch < from_.patch:
            return SemanticVersionSize.DOWNGRADE
        if to.patch > from_.patch:
            return SemanticVersionSize.PATCH
        return SemanticVersionSize.EQUAL


@dataclass(frozen=True)
class ParsedTag:
    version: SemanticVersion | str
    variant: str | None = None

    def __str__(self) -> str:
        base = str(self.version)
        if self.variant:
            return f"{base}-{self.variant}"
        return base


@dataclass(frozen=True)
class ParsedTagAndDigest:
    tag: ParsedTag
    digest: str | None = None

    def __str__(self) -> str:
        if self.digest:
            return f"{self.tag}@{self.digest}"
        return str(self.tag)

    def to_short_string(self) -> str:
        if not self.digest:
            return str(self.tag)
        if self.digest.startswith("sha256:"):
            return f"{self.tag}@{self.digest[7:15]}"
        return f"{self.tag}@{self.digest[:8]}"


@dataclass(frozen=True)
class ParsedImage:
    name: str
    untagged: str
    domain: str | None = None
    namespace: str | None = None
    tag_and_digest: ParsedTagAndDigest | None = None

    def __str__(self) -> str:
        parts = []
        if self.domain:
            parts.append(self.domain)
        if self.namespace:
            parts.append(self.namespace)
        parts.append(self.name)
        ref = ":{}".format(self.tag_and_digest) if self.tag_and_digest else ""
        return "/".join(parts) + ref

    def to_short_string(self) -> str:
        result = self.name
        if self.tag_and_digest:
            result += f":{self.tag_and_digest.to_short_string()}"
        return result

    @staticmethod
    def diff_string(source: "ParsedImage", destination: ParsedTagAndDigest | None) -> str:
        left = source.tag_and_digest.to_short_string() if source.tag_and_digest else "(untagged)"
        right = destination.to_short_string() if destination else "(untagged)"
        return f"{source.name}: {left} → {right}"

@dataclass
class SkopeoInspectResponse:
    """Response from skopeo inspect command"""
    name: str
    digest: str
    created: str
    architecture: str
    os: str
    layers: list[str]
    labels: dict
    env: list[str]
    entrypoint: list[str]
    cmd: list[str]
    working_dir: str
    user: str
