from .state import state
import logging
_logger = logging.getLogger(__name__)

def handle_deployment_webhook(data, event):
    if not event or event.lower() != "pipeline hook":
        return

    if data.get("object_attributes", {}).get("source") != "parent_pipeline":
        return

    commit = data.get("commit", {})
    title = commit.get("title")
    message = commit.get("message")
    state.broadcaster.push(f'{title}: {message}')
