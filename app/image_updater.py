from .models import ParsedImage, ParsedTag, BumpSize, ParsedTagAndDigest
from . import skopeo, image_parser
from .models import SemanticVersion, SemanticVersionSize
from datetime import datetime
from dateutil.parser import isoparse

async def get_sorted_candidate_tags(parsed_active_image: ParsedImage, max_bump_size: BumpSize) -> list[ParsedTag]:
    tags =  await skopeo.list_tags(parsed_active_image.untagged)
    parsed_tags: list[ParsedTag] = []
    for tag in tags:
        parsed_tag = image_parser.try_parse_tag(tag)
        if parsed_tag is not None:
            parsed_tags.append(parsed_tag)

    if parsed_active_image.tag_and_digest is None:
        # for missing tags we will add the latest tag and a digest
        # None -> latest@sha256:123

        valid_tags: list[ParsedTag] = []
        for tag in parsed_tags:
            if tag.version == "latest" and tag.variant is None:
                valid_tags.append(tag)

        return [] if len(valid_tags) == 0 else [valid_tags[0]]

    elif isinstance(parsed_active_image.tag_and_digest.tag.version, str):
        # with releases, we will only add the digest if it dne, or update it if there is a newer one
        # latest -> latest@sha256:123
        # latest@sha256:123 -> latest@sha256:abc
        # we must also match the variant
        # latest-alpine -> latest-alpine@sha256:abc

        release = parsed_active_image.tag_and_digest.tag.version
        variant = parsed_active_image.tag_and_digest.tag.variant

        valid_tags: list[ParsedTag] = []
        for tag in parsed_tags:
            if (isinstance(tag.version, str) and
                tag.version == release and
                tag.variant == variant):
                valid_tags.append(tag)

        return [] if len(valid_tags) == 0 else [valid_tags[0]]

    else:
        # with semver, we will find all the versions that keep the same precision
        # (e.g. we wont do v1.2 -> v2 or v1.2 -> v2.0.0, but we will do v1.2 -> v2.0)
        # then filter them by the configured bump level
        # we must also match the variant
        # v1.2.3-alpine@sha256:abc -> v1.3.1-alpine@sha256:abc

        active_version = parsed_active_image.tag_and_digest.tag.version
        variant = parsed_active_image.tag_and_digest.tag.variant

        valid_versions: list[tuple[SemanticVersion, BumpSize]] = []
        
        for parsed_tag in parsed_tags:
            if not isinstance(parsed_tag.version, SemanticVersion):
                continue
            if parsed_tag.version.version_prefix != active_version.version_prefix:
                continue
            if parsed_tag.variant != variant:
                continue

            size = SemanticVersion.compare(active_version, parsed_tag.version)
            bump_size: BumpSize

            if size == SemanticVersionSize.MAJOR:
                if max_bump_size < BumpSize.MAJOR:
                    continue
                bump_size = BumpSize.MAJOR
            elif size == SemanticVersionSize.MINOR:
                if max_bump_size < BumpSize.MINOR:
                    continue
                bump_size = BumpSize.MINOR
            elif size == SemanticVersionSize.PATCH:
                if max_bump_size < BumpSize.PATCH:
                    continue
                bump_size = BumpSize.PATCH
            elif size == SemanticVersionSize.EQUAL:
                bump_size = BumpSize.DIGEST
            else:
                # SemanticVersionSize.PRECISION_MISMATCH or SemanticVersionSize.DOWNGRADE
                continue

            valid_versions.append((parsed_tag.version, bump_size))

        if len(valid_versions) == 0:
            return []

        # Sort by major, minor, patch in descending order
        sorted_tags = sorted(valid_versions, 
                           key=lambda x: (x[0].major, x[0].minor or -1, x[0].patch or -1), 
                           reverse=True)

        return [ParsedTag(version=sv, variant=variant) for sv, _ in sorted_tags]

def is_upgrade(from_tag_and_digest: ParsedTagAndDigest | None, to_tag: ParsedTag, to_digest: str) -> BumpSize | None:
    """Determine if an upgrade is needed and what bump size it represents"""
    if from_tag_and_digest is None:
        # for missing tags, we will add the latest tag and a digest
        # -> latest@sha256:123
        return BumpSize.DIGEST
    
    elif isinstance(from_tag_and_digest.tag.version, str):
        # with releases, we will only add the digest if it dne, or update it if there is a newer one
        # latest -> latest@sha256:123
        # latest@sha256:123 -> latest@sha256:abc
        # we must also match the variant
        # latest-alpine -> latest-alpine@sha256:abc
        if from_tag_and_digest.digest is None:
            return BumpSize.DIGEST
        if from_tag_and_digest.digest != to_digest:
            return BumpSize.DIGEST
        return None

    elif isinstance(to_tag.version, str):
        raise ValueError(f'Received from tag {from_tag_and_digest} and to tag {to_tag} but they do not have the same version type (semantic and nonsemantic)')
    
    else:
        # with semver, we will find all the versions that keep the same precision
        # (e.g. we wont do v1.2 -> v2 or v1.2 -> v2.0.0, but we will do v1.2 -> v2.0)
        # then filter them by the configured bump level
        # we must also match the variant
        # v1.2.3-alpine@sha256:abc -> v1.3.1-alpine@sha256:abc
        size = SemanticVersion.compare(from_tag_and_digest.tag.version, to_tag.version)
        bump_size: BumpSize

        if size == SemanticVersionSize.MAJOR:
            bump_size = BumpSize.MAJOR
        elif size == SemanticVersionSize.MINOR:
            bump_size = BumpSize.MINOR
        elif size == SemanticVersionSize.PATCH:
            bump_size = BumpSize.PATCH
        elif size == SemanticVersionSize.EQUAL:
            bump_size = BumpSize.DIGEST
        else:
            # SemanticVersionSize.PRECISION_MISMATCH or SemanticVersionSize.DOWNGRADE
            return None

        if from_tag_and_digest.digest is None:
            return bump_size
        if from_tag_and_digest.digest != to_digest:
            return bump_size
        return None

async def get_digest(image: ParsedImage, tag: ParsedTag) -> tuple[str, datetime]:
    inspect = await skopeo.inspect(f'{image.untagged}:{tag}')
    return inspect.digest, isoparse(inspect.created)


