import logging
import google.auth
from google.auth.exceptions import RefreshError, DefaultCredentialsError
import google.auth.transport.requests

logger = logging.getLogger(__name__)

def check_gcloud_auth():
    """Checks Google Cloud authentication and exits if it's invalid."""
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        if hasattr(credentials, "refresh") and not credentials.valid:
            logger.info("Attempting to refresh Google Cloud credentials...")
            credentials.refresh(google.auth.transport.requests.Request())
    except RefreshError:
        logger.error(
            "Reauthentication is needed. Please run `gcloud auth application-default login`."
        )
        exit(1)
    except DefaultCredentialsError:
        logger.error(
            "Could not find valid Google Cloud credentials. Please run `gcloud auth application-default login`."
        )
        exit(1)
