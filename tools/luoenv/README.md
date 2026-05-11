# luoenv — Environment & Secrets Manager

> Manage `.env` files, compare environments, validate required vars, export to multiple formats, and detect secrets in code. Pure Python, zero dependencies.

## Why luoenv?

| Feature | manual `.env` editing | **luoenv** |
|---|---|---|
| List all vars | ✗ | ✓ |
| Mask secret values | ✗ | ✓ |
| Compare two env files | ✗ | ✓ |
| Validate required keys | ✗ | ✓ |
| Export to Docker/K8s | ✗ | ✓ |
| Scan code for secrets | ✗ | ✓ |
| Generate .env.example | ✗ | ✓ |

## Install

```bash
chmod +x luoenv.py
sudo ln -s $(pwd)/luoenv.py /usr/local/bin/luoenv
```

## Usage

```bash
# View
luoenv list                          # list all vars (secrets masked)
luoenv list --secrets                # reveal all values
luoenv list API                      # filter by keyword

# Edit
luoenv get DATABASE_URL              # get specific var
luoenv set API_KEY=abc123            # set a variable
luoenv set HOST=localhost PORT=5432  # set multiple
luoenv unset OLD_LEGACY_VAR

# Compare & Validate
luoenv diff .env .env.staging        # compare two files
luoenv validate                      # check vs .env.example
luoenv validate --keys DB_URL SECRET # check specific keys

# Export
luoenv export                        # shell export statements
luoenv export --format json          # JSON
luoenv export --format docker        # --env flags for docker run
luoenv export --format k8s           # Kubernetes env block

# Security
luoenv scan                          # scan project for hardcoded secrets
luoenv template                      # create .env.example (secrets redacted)
```

## Secret Detection

`luoenv scan` checks your codebase for:
- Passwords and API keys
- AWS/GitHub/bearer tokens
- Private keys and PEM blocks
- Database connection strings
- Hard-coded long secrets

## License
MIT — luokai
