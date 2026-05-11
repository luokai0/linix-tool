#!/usr/bin/env python3
"""
dockerman — Docker container manager (no daemon required)
List, inspect, stop, remove containers and images using the Docker socket

Usage:
  dockerman.py ps                        -- list running containers
  dockerman.py images                  -- list images
  dockerman.py stop <id>               -- stop container
  dockerman.py rm <id>                 -- remove container
  dockerman.py rmi <image>             -- remove image
  dockerman.py logs <id> [lines]        -- show container logs
  dockerman.py stats                   -- live container stats
  dockerman.py pull <image>            -- pull image
"""

import sys
import json
import urllib.request
import urllib.parse

UNIX_SOCKET = 'http+unix://%2Fvar%2Frun%2Fdocker.sock'


def api(path: str, method: str = 'GET', data: str = None) -> dict:
    url = UNIX_SOCKET + urllib.parse.quote(path)
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {'error': str(e)}


def list_containers(all: bool = True) -> list:
    return api(f'/v1.41/containers/json?all={str(all).lower()}')


def list_images() -> list:
    return api('/v1.41/images/json')


def stop_container(container_id: str) -> dict:
    return api(f'/v1.41/containers/{container_id}/stop', 'POST')


def remove_container(container_id: str, force: bool = False) -> dict:
    return api(f'/v1.41/containers/{container_id}?force={str(force).lower()}', 'DELETE')


def remove_image(image: str, force: bool = False) -> dict:
    return api(f'/v1.41/images/{image}?force={str(force).lower()}', 'DELETE')


def get_logs(container_id: str, lines: int = 50) -> dict:
    return api(f'/v1.41/containers/{container_id}/logs?stdout=true&tail={lines}')


def get_stats(container_id: str = '') -> dict:
    return api(f'/v1.41/containers/{container_id}/stats?stream=false')


def pull_image(image: str) -> dict:
    body = json.dumps({'Image': image}).encode()
    return api(f'/v1.41/images/create?fromImage={image}', 'POST', body)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == 'ps':
        for c in list_containers():
            names = c.get('Names', ['?'])[0].lstrip('/')
            img = c.get('Image', '?')
            state = c.get('State', '?')
            cid = c.get('Id', '')[:12]
            print(f"  {cid}  {state:9s}  {names:30s}  {img}")
    elif cmd == 'images':
        for img in list_images():
            tags = img.get('RepoTags', ['<none>'])[0]
            size = int(img.get('Size', 0)) // (1024*1024)
            print(f"  {tags:40s}  {size:6d} MB")
    elif cmd == 'stop' and len(sys.argv) >= 3:
        print(stop_container(sys.argv[2]))
    elif cmd == 'rm' and len(sys.argv) >= 3:
        print(remove_container(sys.argv[2]))
    elif cmd == 'rmi' and len(sys.argv) >= 3:
        print(remove_image(sys.argv[2]))
    elif cmd == 'logs' and len(sys.argv) >= 3:
        lines = int(sys.argv[3]) if len(sys.argv) >= 4 else 50
        result = get_logs(sys.argv[2], lines)
        if isinstance(result, dict) and 'error' in result:
            print(result['error'])
        else:
            print(result)
    elif cmd == 'stats':
        for c in list_containers():
            cid = c.get('Id', '')[:12]
            result = get_stats(cid)
            if isinstance(result, dict) and 'error' not in result:
                mem = result.get('memory_stats', {}).get('usage', 0) // (1024*1024)
                cpu = result.get('cpu_stats', {}).get('cpu_usage', {}).get('total_usage', 0)
                print(f"  {cid}  mem={mem}MB  cpu={cpu}")
    elif cmd == 'pull' and len(sys.argv) >= 3:
        print(pull_image(sys.argv[2]))
    else:
        print(__doc__)