# Nepal Flood Infrastructure Impact Map

An interactive map for exploring infrastructure damage assessments from the Copernicus Emergency Management Service (CEMS) activation for flooding in Nepal.

The app helps users search, filter, and visually inspect assessed roads, bridges, power plants, airfields, heliports, and other infrastructure.

## Data

Data is retrieved from the [Copernicus Emergency Management Service](https://mapping.emergency.copernicus.eu/activations/EMSR927/) activation `EMSR927`.

The API caches fetched data for one hour. The interface distinguishes between the source event date and when this application last refreshed its cache.

## Run locally

### Development with hot reload

```bash
make up
```

Open [http://localhost:5173](http://localhost:5173).

This starts the Vite frontend with hot module reload and the FastAPI backend with automatic reload.

### Production-style API

```bash
make up-prod
```

Open [http://localhost:8000](http://localhost:8000).

### Stop services

```bash
make down
```

## Local development without Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

In a second terminal:

```bash
npm install
npm run dev
```

## API endpoints

- `GET /health` — service health check
- `GET /api/infrastructure/search` — search and filter infrastructure features
- `GET /api/infrastructure/summary` — infrastructure and damage summary statistics
- `GET /docs` — interactive FastAPI documentation

## Links

- [GitHub repository](https://github.com/sraddhanjali/nepal-flood-map)
- [LinkedIn](https://www.linkedin.com/in/sraddhanjali/)
- [Nepal Hackathon](https://www.nepalhackathon.org/)
- [Donate To Nepal](https://pmdrf.nchl.com.np/index.html)

## License

MIT
