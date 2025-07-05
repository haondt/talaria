import re
from .config import config
from .models import ParsedImage, ParsedTag, ParsedTagAndDigest, SemanticVersion

DEFAULT_DOMAIN_NAMESPACE = "library"
DEFAULT_DOMAIN = "docker.io"

_valid_releases = "|".join(re.escape(r) for r in config.valid_releases.split('|'))

_tag_pattern = (
    rf"(?P<versionprefix>v)?(?:(?:(?P<major>\d{{1,6}})"
    rf"(?:\.(?P<minor>\d{{1,6}})(?:\.(?P<patch>\d{{1,6}}))?)?)|(?P<release>{_valid_releases}))"
    r"(?:-(?P<variant>\w+))?"
)
_tag_and_digest_pattern = rf"(?P<tag>{_tag_pattern})(?:@(?P<digest>sha\d+:[a-f0-9]+))?"
_image_pattern = (
    rf"(?P<untagged>(?:(?P<domain>[\w.\-_]+\.[\w.\-_]+(?::\d+)?)/)?"
    rf"(?:(?P<namespace>(?:[\w.\-_]+)(?:/[\w.\-_]+)*)/)?"
    rf"(?P<name>[a-z0-9.\-_]+))"
    rf"(?::(?P<taganddigest>{_tag_and_digest_pattern}))?"
)

_image_regex = re.compile(f"^{_image_pattern}$")
_tag_and_digest_regex = re.compile(f"^{_tag_and_digest_pattern}$")
_tag_regex = re.compile(f"^{_tag_pattern}$")


def parse(image: str, insert_default_domain: bool = True) -> ParsedImage:
    parsed = try_parse(image, insert_default_domain)
    if parsed:
        return parsed
    raise ValueError(f"Unable to parse image {image}")


def try_parse(image: str, insert_default_domain: bool = True) -> ParsedImage | None:
    match = _image_regex.match(image)
    if not match:
        return None

    domain = _get_group(match, "domain")
    namespace = _get_group(match, "namespace")
    name = _get_group(match, "name")
    untagged = _get_group(match, "untagged")

    if not name or not untagged:
        return None

    if insert_default_domain and not domain:
        domain = DEFAULT_DOMAIN
        if not namespace:
            namespace = DEFAULT_DOMAIN_NAMESPACE

    tag_and_digest = _try_parse_tag_and_digest(match)

    return ParsedImage(
        domain=domain,
        namespace=namespace,
        name=name,
        untagged=untagged,
        tag_and_digest=tag_and_digest,
    )


def try_parse_tag_and_digest(text: str) -> ParsedTagAndDigest | None:
    match = _tag_and_digest_regex.match(text)
    if not match:
        return None
    return _try_parse_tag_and_digest(match)


def _try_parse_tag_and_digest(match: re.Match) -> ParsedTagAndDigest | None:
    digest = _get_group(match, "digest")
    tag = _try_parse_tag(match)
    if not tag:
        return None
    return ParsedTagAndDigest(tag=tag, digest=digest)


def try_parse_tag(text: str) -> ParsedTag | None:
    match = _tag_regex.match(text)
    if not match:
        return None
    return _try_parse_tag(match)


def _try_parse_tag(match: re.Match) -> ParsedTag | None:
    major = _get_group(match, "major")
    if major:
        version = SemanticVersion(
            version_prefix=_get_group(match, "versionprefix"),
            major=int(major),
            minor=_parse_int_group(match, "minor"),
            patch=_parse_int_group(match, "patch"),
        )
    elif release := _get_group(match, "release"):
        version = release
    else:
        return None

    variant = _get_group(match, "variant")
    return ParsedTag(version=version, variant=variant)


def _get_group(match: re.Match, key: str) -> str | None:
    return match.groupdict().get(key) or None


def _parse_int_group(match: re.Match, key: str) -> int | None:
    val = _get_group(match, key)
    return int(val) if val is not None else None
