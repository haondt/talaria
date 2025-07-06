import time
from .state import PipelineStatus, state
import logging
_logger = logging.getLogger(__name__)

def handle_deployment_webhook(data, event):
    if not event or event.lower() != "pipeline hook":
        return

    # discard child pipelines
    if data.get("object_attributes", {}).get("source") == "parent_pipeline":
        return

    # discard incomplete pipelines
    status = data.get("object_attributes", {}).get("status")
    if status not in ['success', 'failed']:
        return

    # discard pipelines instigated by other sources
    sha = data.get("object_attributes", {}).get("sha")
    if sha is None:
        return
    commit = state.commit.get(sha)
    if commit is None:
        return 

    if status == "success":
        commit.pipeline_status = PipelineStatus.SUCCESS
    else:
        commit.pipeline_status = PipelineStatus.FAILURE

    commit.commit_url = data.get("commit", {}).get("url")
    commit.pipeline_url = data.get("object_attributes", {}).get("url")
    commit.pipeline_timestamp = time.time()
    commit.pipeline_duration = data.get("object_attributes", {}).get("duration")

    state.commit[sha] = commit

