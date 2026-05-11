# jsontool — CLI JSON Processor

Query, transform, validate, and format JSON from the command line.

## Features

- **parse** — Pretty-print JSON
- **query** — Dot-path query (e.g. `data.users[0].name`)
- **validate** — Check if a file is valid JSON
- **tocsv** — Convert JSON array of objects to CSV
- **merge** — Deep-merge two JSON files
- **flatten** — Flatten nested JSON to dot-notation

## Usage

```bash
python3 jsontool.py parse data.json
python3 jsontool.py query data.json "users[0].name"
python3 jsontool.py validate data.json
python3 jsontool.py tocsv data.json > data.csv
python3 jsontool.py merge a.json b.json
python3 jsontool.py flatten data.json
```

## License

MIT — luokai