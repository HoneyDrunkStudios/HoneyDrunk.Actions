"""Read-only, fail-closed traffic contract for Container App rollouts."""

import json
import os
import re
import subprocess
import sys


def current_revision(traffic, app_name, expected_revision=None):
    """Require one named 100% target; never guess from revision creation order."""
    if not isinstance(traffic, list) or not traffic:
        raise ValueError("Traffic must contain one explicit revision at 100%")
    targets = []
    for entry in traffic:
        if not isinstance(entry, dict):
            raise ValueError("Traffic entries must be objects")
        weight = entry.get("weight", entry.get("trafficWeight"))
        if type(weight) is not int or not 0 <= weight <= 100:
            raise ValueError("Traffic weights must be integers between 0 and 100")
        if "weight" in entry and "trafficWeight" in entry and entry["trafficWeight"] != weight:
            raise ValueError("Traffic entry has conflicting weights")
        latest = entry.get("latestRevision", False)
        if type(latest) is not bool:
            raise ValueError("latestRevision must be a boolean")
        if not weight:
            continue
        if latest:
            raise ValueError("Positive latestRevision traffic is unsafe: pin the verified serving revision before rollout")
        revision = entry.get("revisionName", "")
        if not isinstance(revision, str) or not re.fullmatch(re.escape(app_name) + r"--[a-z0-9][a-z0-9-]*", revision):
            raise ValueError("Positive traffic must name a revision belonging to the target app")
        targets.append((revision, weight))
    if len(targets) != 1 or targets[0][1] != 100:
        raise ValueError("Exactly one explicitly named revision must receive 100% traffic; consolidate split traffic before rollout")
    revision = targets[0][0]
    if expected_revision is not None and revision != expected_revision:
        raise ValueError("Traffic target changed during deployment; stop and review the active rollout or rollback")
    return revision


def main():
    try:
        result = subprocess.run(
            ["az", "containerapp", "ingress", "traffic", "show",
             "--name", os.environ["APP_NAME"],
             "--resource-group", os.environ["RESOURCE_GROUP"], "--output", "json"],
            check=True, capture_output=True, text=True,
        )
        revision = current_revision(json.loads(result.stdout), os.environ["APP_NAME"],
                                    os.environ.get("EXPECTED_REVISION"))
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        # Do not replace API errors with empty traffic or dump the raw Azure response.
        print(f"::error::Cannot establish safe Container App traffic: {error}", file=sys.stderr)
        return 1
    print(revision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
