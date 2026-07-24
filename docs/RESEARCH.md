# Source and provider research

Verified for this release on 23 July 2026.

## Official protected-area data

### FUNAI

Official portal:

- https://www.gov.br/funai/pt-br/atuacao/terras-indigenas/geoprocessamento-e-mapas
- https://www.gov.br/funai/pt-br/atuacao/terras-indigenas/geoprocessamento-e-mapas/geprocessamento

FUNAI states that its geospatial data is updated monthly and exposes the national polygon Shapefile through a WFS `GetFeature` request for `Funai:tis_poligonais`.

### MMA / CNUC

Official dataset:

- https://dados.mma.gov.br/dataset/unidadesdeconservacao
- CKAN package ID: `44b6dc8a-dc82-4a84-8d95-1b0da7c85dac`
- official March 2026 polygon fallback resource ID: `b1f7a269-a0b2-4a81-9ac5-108905e74a00`

The application queries CKAN metadata so a newer suitable polygon ZIP can supersede the fallback without a code release.

## Flight providers

### ADSB.lol

- https://www.adsb.lol/docs/open-data/api/

Public open-data API and default PoC source. The project treats it as best-effort because no public SLA or explicit production request allowance is documented.

### Airplanes.live

- https://airplanes.live/api-guide/
- https://airplanes.live/api/

Public point/radius API intended for non-commercial use, rate limited to one request per second, without an SLA. The public free allowance is 500 requests per day; the application enforces that ceiling.

### ADS-B Exchange Enterprise

- https://www.adsbexchange.com/api/aircraft/v2/docs

Enterprise radius queries expose readsb-style aircraft data. Official examples use the `api-auth` request header. Enterprise access is paid.

### Flightradar24 API

- https://fr24api.flightradar24.com/docs/authentication
- https://fr24api.flightradar24.com/docs/endpoints/overview
- https://fr24api.flightradar24.com/docs/credit-overview
- https://fr24api.flightradar24.com/docs/storage-rules

Uses bearer authentication and `Accept-Version: v1`. Live full-position records can include route, operator, registration, type, and source fields. Credits are charged by returned records, and retained API data is subject to the provider’s storage limits. The application stores only event/state snapshots and requires an ICAO hex for cross-provider merging.

### FlightAware

- https://www.flightaware.com/commercial/aeroapi/

AeroAPI offers current track/position data. It remains a possible enterprise/enrichment adapter, but was not included because the radius/bounds APIs above fit the initial geofencing design more directly and FlightAware licensing/pricing depends on use category.

### OpenSky

- https://opensky-network.org/about/terms-of-use

Not integrated because operational automated REST use requires appropriate written licensing under the current terms.

## Email and infrastructure

### Resend idempotency

- https://resend.com/docs/dashboard/emails/idempotency-keys

The application supplies one stable idempotency key per event to reduce duplicate sends after ambiguous network failures.

### Caddy

- https://caddyserver.com/docs/automatic-https
- https://caddyserver.com/docs/quick-starts/reverse-proxy
- https://hub.docker.com/_/caddy

The optional Compose profile uses the official Caddy image as a reverse proxy with automatic certificate management and HTTPS redirects for a configured public domain.

### Docker hardening references

- https://docs.docker.com/reference/compose-file/services/
- https://docs.docker.com/engine/security/

The app container uses a non-root process, read-only filesystem, dropped capabilities, no-new-privileges, PID limits, and explicit writable volumes/tmpfs.
