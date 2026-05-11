# dockerman — Docker Container Manager

Manage Docker containers via the REST API (no CLI daemon required).

## Features

- **ps** — List containers (running + stopped)
- **images** — List local images
- **stop** — Stop a container
- **rm** — Remove a container
- **rmi** — Remove an image
- **logs** — Fetch container logs
- **stats** — Show container resource usage
- **pull** — Pull an image

## Usage

```bash
python3 dockerman.py ps
python3 dockerman.py images
python3 dockerman.py stop 3e4a5b
python3 dockerman.py rm 3e4a5b
python3 dockerman.py logs 3e4a5b 100
python3 dockerman.py stats
python3 dockerman.py pull nginx:latest
```

Note: Requires access to `/var/run/docker.sock`. Run as root or add user to docker group.

## License

MIT — luokai