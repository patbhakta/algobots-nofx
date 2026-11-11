"""Replace the two paper containers with a tested image, retaining stopped rollback copies.

Run on the Docker host. No broker credentials or orders are created. Existing
environment, command, bind mounts and restart policy are preserved. Roll back
both containers if Docker cannot start either replacement. Readiness still
requires the gateway/full-loop checks after this command.
"""

import argparse
import json
import subprocess
from datetime import UTC, datetime

NAMES = ("nautilus-node", "algobots-deployment-supervisor")


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", required=True)
    ap.add_argument("--suffix", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    docker("image", "inspect", args.image)
    plans = []
    for name in NAMES:
        config = json.loads(docker("inspect", name))[0]
        networks = config["NetworkSettings"]["Networks"]
        assert len(networks) == 1, "multiple networks require explicit migration"
        host = config["HostConfig"]
        assert not host["PortBindings"], "unexpected published ports"
        assert not any(host.get(k) for k in ("Memory", "NanoCpus", "CpuQuota", "Privileged", "CapAdd")), (
            "custom resource/security options require explicit migration"
        )
        assert all(m["Type"] == "bind" for m in config["Mounts"])
        assert config["State"]["Running"], f"{name} is not running"
        backup = f"{name}-{args.suffix}"
        assert backup not in docker("ps", "-a", "--format", "{{.Names}}").splitlines()
        cmd = ["create", "--name", name, "--network", next(iter(networks))]
        for env in config["Config"]["Env"]:
            cmd += ["--env", env]
        for mount in config["Mounts"]:
            cmd += ["--volume", mount["Source"] + ":" + mount["Destination"]
                    + ("" if mount["RW"] else ":ro")]
        policy = config["HostConfig"]["RestartPolicy"]["Name"]
        if policy:
            cmd += ["--restart", policy]
        for option, key in [("--user", "User"), ("--workdir", "WorkingDir")]:
            if config["Config"].get(key):
                cmd += [option, config["Config"][key]]
        cmd += [args.image, *config["Config"]["Cmd"]]
        plans.append((name, backup, cmd))
    print(json.dumps({"image": args.image, "containers": list(NAMES), "apply": args.apply}))
    if not args.apply:
        return
    renamed = []
    try:
        for name, backup, cmd in plans:
            docker("stop", "--time", "45", name)
            docker("rename", name, backup)
            renamed.append((name, backup))
            docker(*cmd)
            docker("start", name)
            assert json.loads(docker("inspect", name))[0]["State"]["Running"]
            print(name, "started", datetime.now(UTC).isoformat(), "rollback", backup)
    except Exception:
        for name, backup in reversed(renamed):
            if name in docker("ps", "-a", "--format", "{{.Names}}").splitlines():
                docker("stop", "--time", "45", name)
                docker("rename", name, name + "-failed-" + args.suffix)
            docker("rename", backup, name)
            docker("start", name)
        raise


if __name__ == "__main__":
    main()
