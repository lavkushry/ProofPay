"""Prove the running Compose runner can reach services but cannot reach DB/Internet."""

import argparse
import json
import subprocess


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    args = parser.parse_args()
    compose = ["docker", "compose"] + (["-p", args.project] if args.project else [])
    runner_id = command(*compose, "ps", "-q", "runner")
    db_id = command(*compose, "ps", "-q", "db")
    assert runner_id and db_id, "Start Compose with --profile verification first"
    runner = json.loads(command("docker", "inspect", runner_id))[0]
    database = json.loads(command("docker", "inspect", db_id))[0]
    networks = runner["NetworkSettings"]["Networks"]
    assert len(networks)==1
    network_id = next(iter(networks.values()))["NetworkID"]
    assert json.loads(command("docker", "network", "inspect", network_id))[0]["Internal"]
    assert not set(networks) & set(database["NetworkSettings"]["Networks"])
    host = runner["HostConfig"]
    assert host["ReadonlyRootfs"] and host["CapDrop"]==["ALL"]
    assert "no-new-privileges:true" in host["SecurityOpt"]
    assert host["Memory"]==768*1024*1024 and host["NanoCpus"]==1000000000 and host["PidsLimit"]==256
    assert runner["Config"]["User"]=="pwuser"
    environment = {item.split("=", 1)[0] for item in runner["Config"]["Env"]}
    assert not any("DATABASE" in key or "PAYPAL" in key or key.endswith("API_KEY") for key in environment)
    db_ip = next(iter(database["NetworkSettings"]["Networks"].values()))["IPAddress"]
    probe = '''
import socket, sys
import httpx
with httpx.Client(timeout=5, trust_env=False) as client:
    assert client.get("http://api:8000/readyz").status_code==200
    assert client.get("http://fixture:8080/manifest").status_code==200
for target in ((sys.argv[1], 5432), ("1.1.1.1", 443)):
    try:
        connection = socket.create_connection(target, timeout=2)
    except OSError:
        continue
    connection.close()
    raise AssertionError("Runner reached a forbidden network target")
print("Runner API/fixture reachability passed; database and public egress blocked.")
'''
    print(command("docker", "exec", runner_id, "python", "-c", probe, db_ip))


if __name__=="__main__":
    main()
