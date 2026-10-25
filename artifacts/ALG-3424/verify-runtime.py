"""Run on .243; report runtime/auth facts without printing the token."""

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

info = json.loads(subprocess.check_output(["docker", "inspect", "marimo-quantlab"]))[0]
command = info["Config"]["Cmd"]
token = command[command.index("--token-password") + 1]
base = "http://100.82.57.72:8205/api/files/roots"


def status(url):
    try:
        with urllib.request.urlopen(url) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


unauth = status(base)
auth = status(base + "?" + urllib.parse.urlencode({"access_token": token}))
ports = info["NetworkSettings"]["Ports"]["2718/tcp"]
assert ports == [{"HostIp": "100.82.57.72", "HostPort": "8205"}], ports
assert (unauth, auth) == (401, 200), (unauth, auth)
assert info["Config"]["User"] == "1000:1000"
assert info["State"]["Health"]["Status"] == "healthy"
print(
    json.dumps(
        dict(
            user=info["Config"]["User"],
            health="healthy",
            ports=ports,
            unauthenticated=unauth,
            authenticated=auth,
        ),
        sort_keys=True,
    )
)
root = Path("/mnt/funnytree-quantlab/algobots")
for relative in [
    "openbb_store/manifests/external/openbb-spy-daily/openbb-spy-ad6a2491f1d84484.json",
    "ntl_catalog/openbb-spy-ad6a2491f1d84484",
]:
    path = root / relative
    stat = path.stat()
    print(
        json.dumps(
            dict(path=relative, uid=stat.st_uid, gid=stat.st_gid, mode=oct(stat.st_mode & 0o7777))
        )
    )
