import logging
import asyncio
import time
from dataclasses import replace

from .models import DockerComposeTarget, ParsedImage, ParsedTagAndDigest

from . import image_updater
from . import image_parser
from . import skopeo
from . import config
from . import talaria_git as git
from .state import CommitInfo, PipelineStatus, state
from . import docker_compose_file
_logger = logging.getLogger(__name__)

def start():
    _logger.info("Starting scanner...")
    asyncio.create_task(_start())
    _logger.info("Scanner started.")

async def _start():
    delay = config.update_delay.total_seconds()

    while True:
        now = time.time()
        next_run = state.next_run

        if next_run is None or next_run <= now:
            _logger.info("Scheduled time reached or not set. Running scan.")
            await _run_scan(delay)
            continue

        timeout = max(0, next_run - now)
        try:
            cmd = await asyncio.wait_for(state.scanner_message_queue.get(), timeout=timeout)
            if cmd == "scan_now":
                _logger.info("Immediate scan requested.")
                await _run_scan(delay)
        except asyncio.TimeoutError:
            _logger.info("Scheduled scan triggered by timeout.")
            await _run_scan(delay)

async def _run_scan(delay):
    try:
        _logger.info("Running scan...")

        repo = git.TalariaGit()
        repo.delete()
        await repo.clone()
        await repo.setup_environment()

        docker_compose_files: list[str] = docker_compose_file.get_docker_compose_files()
        targets: list[DockerComposeTarget] = []
        for file in docker_compose_files:
            potential_targets, errors = docker_compose_file.get_images(file)
            for error in errors:
                _logger.warning(f'Unable to parse docker compose file image in file {file}: {error}')
            for target in potential_targets:
                if target.skip:
                    _logger.info(f'Skipping image {target.service_key} due to configured skip')
                else:
                    targets.append(target)

        async def update_target(target) -> tuple[DockerComposeTarget, ParsedImage, ParsedImage] | None:
            parsed_image = image_parser.try_parse(target.current_image_string)
            if not parsed_image:
                _logger.warn(f'Failed to parse image {target.current_image_string}')
                return

            _logger.info(f'Checking for updates for {parsed_image}')

            candidate_tags = await image_updater.get_sorted_candidate_tags(parsed_image, target.bump)
            _logger.debug(f'Found {len(candidate_tags)} candidate tags for target {parsed_image} with bump size {target.bump}.')
            if len(candidate_tags) == 0:
                return

            desired_tag = candidate_tags[0]
            _logger.debug(f'Using desired tag {desired_tag} for target {parsed_image} with bump size {target.bump}.')
            digest, created = await image_updater.get_digest(parsed_image, desired_tag)
            if image_updater.is_upgrade(parsed_image.tag_and_digest, desired_tag, digest) is None:
                _logger.debug(f'Determined desired tag {desired_tag} with digest {digest} for target {parsed_image} is not an upgrade.')
                return 

            new_image = replace(parsed_image, 
                tag_and_digest=ParsedTagAndDigest(
                    tag=desired_tag,
                    digest=digest
                )
            )
            _logger.info(f'Found upgrade {ParsedImage.diff_string(parsed_image, new_image.tag_and_digest)}')
            return (target, parsed_image, new_image)

        get_updates_tasks = [update_target(t) for t in targets]
        results = await asyncio.gather(*get_updates_tasks)
        results = [i for i in results if i is not None]

        _logger.info(f'Found {len(results)} updates. Taking the first {config.maximum_concurrent_pushes}.')
        results = results[:config.maximum_concurrent_pushes]

        if len(results) > 0:
            _logger.info('Applying changes to git repo')
            commit_title = "[talaria] Updating images"
            changes = []
            for (target, old_image, new_image) in results:
                docker_compose_file.apply_update(target, str(new_image))
                changes.append(ParsedImage.diff_string(old_image, new_image.tag_and_digest))
            commit_body = '\n'.join(changes)

            await repo.add()
            await repo.commit(commit_title, commit_body)
            await repo.push()

            sha = await repo.get_current_commit()
            state.commit[sha] = CommitInfo(
                commit_hash=sha,
                commit_short_hash=await repo.get_short_commit(),
                commit_url=None,
                commit_timestamp=time.time(),
                pipeline_url=None,
                pipeline_status=PipelineStatus.UNKNOWN,
                pipeline_timestamp=None,
                pipeline_duration=None
            )

        _logger.info("Scan complete.")
    except Exception as e:
        _logger.exception(f"Scan failed. {type(e).__name__}: {e}")
    finally:
        state.next_run = time.time() + delay
