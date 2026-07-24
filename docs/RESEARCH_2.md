I have not changed the application code.

## What appears to be failing

The problem is partly with the upstream delivery systems rather than the polygons themselves:

* FUNAI still publishes monthly updated Indigenous-territory data, but its download links pass through `geoserver.funai.gov.br`; the official page even advises manually using “Save link as” when downloads do not start, which suggests the service is not designed as a dependable automated feed. ([Serviços e Informações do Brasil][1])
* The latest CNUC March 2026 resource exists in the MMA catalogue, but opening its resource page currently redirects to an unrelated MMA “Defeso” application. ([dados.mma.gov.br][2])

The safest strategy is therefore a **source fallback chain**, rather than depending on one government URL.

# Recommended sources

## 1. Indigenous territories: RAISG/ISA ArcGIS REST

This is the strongest immediately usable alternative.

The Instituto Socioambiental/RAISG service exposes a public polygon layer for Amazonian Indigenous territories. It supports:

* GeoJSON;
* JSON and PBF;
* attribute filtering;
* pagination;
* a maximum of 2,000 records per request;
* fields for country, name, category, status, peoples, source and data-update date. ([geo2.socioambiental.org][3])

The endpoint currently exposes a public ArcGIS REST service without requiring a login:

```text
https://geo2.socioambiental.org/raisg/rest/services/raisg/raisg_tis/MapServer/1/query
```

Example GeoJSON request:

```bash
curl --get \
  'https://geo2.socioambiental.org/raisg/rest/services/raisg/raisg_tis/MapServer/1/query' \
  --data-urlencode "where=pais='Brasil'" \
  --data-urlencode 'outFields=*' \
  --data-urlencode 'returnGeometry=true' \
  --data-urlencode 'outSR=4326' \
  --data-urlencode 'f=geojson' \
  --data-urlencode 'resultOffset=0' \
  --data-urlencode 'resultRecordCount=2000' \
  --output indigenous-territories-brazil.geojson
```

RAISG also offers downloadable Indigenous-territory Shapefiles dated June 2025. ([RAISG][4])

### Assessment

**Recommended operational fallback for Indigenous territories.**

Advantages:

* simple GeoJSON response;
* stable ArcGIS API conventions;
* useful status and provenance fields;
* coverage across the entire Amazon;
* maintained by a well-established socio-environmental network.

Limitation:

* it is not necessarily as current as FUNAI’s monthly source;
* the application should retain RAISG’s `fuente` and `fecha_atualizacion_dato` fields;
* FUNAI should remain the legal-reference source when boundaries or status are contested.

## 2. Indigenous territories: current ArcGIS FUNAI mirror

A current ArcGIS Online item titled **“Terras Indígenas do Brasil — Delimitações Oficiais FUNAI”** is also available. It describes boundaries, modalities and regularization phases managed by FUNAI. ([ArcGIS][5])

Item:

```text
https://www.arcgis.com/home/item.html?id=78ba481fb2904ebb9e708d9ef4a2a462&sublayer=0
```

This could provide a more recent snapshot than RAISG.

### Assessment

**Promising secondary source, but verify its owner and item metadata before treating it as authoritative.**

I would use it to:

* compare feature counts against RAISG;
* check recent phase changes;
* obtain a snapshot when the FUNAI GeoServer is unavailable.

I would not silently replace a known-good dataset solely from an ArcGIS item without checking:

* item owner;
* source attribution;
* last modified date;
* number of polygons;
* status fields;
* geographic extent.

## 3. Federal conservation units: ICMBio WFS

For **federal conservation units**, ICMBio has the strongest alternative official service.

ICMBio provides:

* a direct WFS through INDE;
* a direct Shapefile download;
* data updated on **June 30, 2026**. ([Serviços e Informações do Brasil][6])

WFS endpoint:

```text
https://geoservicos.inde.gov.br/geoserver/ICMBio/ows
```

Capabilities test:

```bash
curl --fail --location \
  'https://geoservicos.inde.gov.br/geoserver/ICMBio/ows?service=WFS&version=2.0.0&request=GetCapabilities' \
  --output icmbio-wfs-capabilities.xml
```

GeoJSON download pattern:

```bash
curl --get \
  'https://geoservicos.inde.gov.br/geoserver/ICMBio/ows' \
  --data-urlencode 'service=WFS' \
  --data-urlencode 'version=2.0.0' \
  --data-urlencode 'request=GetFeature' \
  --data-urlencode 'typeNames=ICMBio:limiteucsfederais_a' \
  --data-urlencode 'outputFormat=application/json' \
  --data-urlencode 'srsName=EPSG:4326' \
  --output icmbio-federal-protected-areas.geojson
```

### Assessment

**Recommended primary source for federal UCs.**

Its important limitation is scope: ICMBio’s national layer does not by itself replace CNUC coverage of all state and municipal units. The ICMBio page also treats some older non-georeferenced RPPNs as approximate circles rather than exact boundaries. ([Serviços e Informações do Brasil][6])

## 4. All conservation units: direct CNUC snapshot

CNUC remains the correct official unified source for federal, state and municipal conservation units.

Although the latest March 2026 resource page is currently malfunctioning, older direct static files bypass the broken catalogue interface. For example, MMA’s indexed August 2025 archive has a direct ZIP URL. ([dados.mma.gov.br][7])

```text
https://dados.mma.gov.br/dataset/44b6dc8a-dc82-4a84-8d95-1b0da7c85dac/resource/6ba9a557-87e8-4882-acb7-b3e0f0ea192d/download/shp_cnuc_2025_08.zip
```

### Assessment

**Recommended stable official snapshot while the March 2026 download is unavailable.**

It is older than ideal, but preferable to silently having no conservation areas. Its schema includes UC code, name, administrative sphere and state information. ([dados.mma.gov.br][8])

A reasonable hierarchy would be:

1. CNUC March 2026 direct archive, once its actual file URL is recovered;
2. CNUC August 2025 static archive;
3. ICMBio June 2026 overlay for updated federal boundaries;
4. RAISG or Protected Planet for comparison and gap detection.

## 5. National and state protected areas: RAISG ArcGIS REST

RAISG also exposes protected-area layers through ArcGIS REST:

```text
https://geo2.socioambiental.org/raisg/rest/services/raisg/raisg_anps_N/MapServer
```

Available polygon layers include:

* layer `1`: departmental/subnational protected areas;
* layer `2`: national protected areas. ([geo2.socioambiental.org][9])

Queries:

```text
https://geo2.socioambiental.org/raisg/rest/services/raisg/raisg_anps_N/MapServer/1/query
https://geo2.socioambiental.org/raisg/rest/services/raisg/raisg_anps_N/MapServer/2/query
```

Example:

```bash
curl --get \
  'https://geo2.socioambiental.org/raisg/rest/services/raisg/raisg_anps_N/MapServer/2/query' \
  --data-urlencode "where=pais='Brasil'" \
  --data-urlencode 'outFields=*' \
  --data-urlencode 'returnGeometry=true' \
  --data-urlencode 'outSR=4326' \
  --data-urlencode 'f=geojson' \
  --output raisg-brazil-national-protected-areas.geojson
```

The service supports GeoJSON and pagination and exposes fields for category, name, administrative scope, status, source and update date. ([geo2.socioambiental.org][9])

However, the service description says that the Brazil national layer was compiled from 2019 materials. Although RAISG separately offers downloadable protected-area data dated June 2025, the exact age needs to be checked at the feature level. ([geo2.socioambiental.org][10])

### Assessment

**Good continuity fallback; not suitable as the sole source of current legal boundaries.**

## 6. Protected Planet

Protected Planet maintains the global World Database on Protected and Conserved Areas and updates it monthly. It supports downloads and a version 4 API. ([protectedplanet.net][11])

The API requires a free token:

```text
https://api.protectedplanet.net/v4/
```

Protected-area and parcel endpoints are available, including granular polygon parcels. ([api.protectedplanet.net][12])

### Assessment

**Best international fallback and cross-check.**

Advantages:

* monthly updates;
* national and subnational areas;
* standardized international schema;
* downloadable geometries.

Limitations:

* requires a token;
* reported Brazilian data may lag local legal changes;
* its terms require attribution and contain reuse conditions;
* it should not replace official Brazilian sources for legal interpretation. ([protectedplanet.net][13])

# Recommended fallback chain

## Indigenous territories

```text
1. FUNAI monthly official data
        ↓ unavailable
2. RAISG/ISA ArcGIS REST
        ↓ validation or newer comparison
3. ArcGIS “Delimitações Oficiais FUNAI” snapshot
        ↓ emergency only
4. Last known-good local snapshot
```

## Conservation units

```text
1. Current CNUC official archive
        ↓ unavailable
2. Last downloadable CNUC static archive
        +
   ICMBio WFS for fresher federal boundaries
        ↓ gaps/cross-check
3. RAISG national + subnational layers
        ↓ external fallback
4. Protected Planet
        ↓
5. Last known-good local snapshot
```

# What I would use immediately

For a first operational deployment:

| Dataset                            | Immediate source                                 |
| ---------------------------------- | ------------------------------------------------ |
| Indigenous territories             | RAISG ArcGIS REST                                |
| Federal conservation units         | ICMBio WFS, June 2026                            |
| State/municipal conservation units | CNUC August 2025 static ZIP                      |
| Validation layer                   | Protected Planet or RAISG protected areas        |
| Authoritative provenance           | Preserve FUNAI/CNUC identifiers and source dates |

This gives you a complete-enough working dataset without depending on the two failing download routes.

## Validation before accepting any replacement

Regardless of source, I would require the downloaded result to pass:

* expected geometry type is Polygon or MultiPolygon;
* valid CRS and conversion to EPSG:4326;
* non-empty feature collection;
* plausible feature count;
* coverage intersects PA, AM, AP or RR;
* no extreme drop in total area;
* unique or stable source identifiers;
* geometry repair does not remove substantial areas;
* source and update date retained per feature;
* previous healthy snapshot remains available.

A new dataset should not replace the current one when:

* feature count drops by more than roughly 10%;
* combined area changes unexpectedly;
* all status or name fields are empty;
* the source returns an HTML error page disguised as a ZIP;
* only point geometries are returned;
* the archive contains no `.shp`, `.shx` or `.dbf`;
* the service reports success but returns zero Brazilian records.

The strongest practical combination is therefore **RAISG for Indigenous territories, ICMBio for federal UCs, and a static CNUC snapshot for the remaining conservation units**, with Protected Planet as an independent comparison source.

[1]: https://www.gov.br/funai/pt-br/atuacao/terras-indigenas/geoprocessamento-e-mapas "Terras Indígenas: Dados Geoespaciais e Mapas"
[2]: https://dados.mma.gov.br/ne/dataset/unidadesdeconservacao/resource/b1f7a269-a0b2-4a81-9ac5-108905e74a00 "Unidades de Conservação - CNUC_2026_03"
[3]: https://geo2.socioambiental.org/raisg/rest/services/raisg/raisg_tis/MapServer "raisg/raisg_tis (MapServer)"
[4]: https://www.raisg.org/en/maps/ "Maps – RAISG"
[5]: https://www.arcgis.com/home/item.html?id=78ba481fb2904ebb9e708d9ef4a2a462&sublayer=0 "Terras Indígenas do Brasil — Delimitações Oficiais FUNAI"
[6]: https://www.gov.br/icmbio/pt-br/dados-icmbio/dados_geoespaciais/mapa-tematico-e-dados-geoestatisticos-das-unidades-de-conservacao-federais "Dados geoespaciais de referência da Cartografia Nacional e dados temáticos produzidos no ICMBio — Instituto Chico Mendes de Conservação da Biodiversidade"
[7]: https://dados.mma.gov.br/en/dataset/unidadesdeconservacao/resource/6ba9a557-87e8-4882-acb7-b3e0f0ea192d "Unidades de Conservação - Polígono CNUC 2025_08"
[8]: https://dados.mma.gov.br/dataset/44b6dc8a-dc82-4a84-8d95-1b0da7c85dac/resource/1f50ca6b-f045-4c79-b172-33c58a59e667/download/dicionario-de-dados-unidades-de-conservacao.pdf "Ministério do Meio Ambiente – Dicionário de Dados"
[9]: https://geo2.socioambiental.org/raisg/rest/services/raisg/raisg_anps_N/MapServer "raisg/raisg_anps_N (MapServer)"
[10]: https://geo2.socioambiental.org/raisg/rest/services/raisg/raisg_anps_N/MapServer/2 "Layer: Áreas Naturales Protegidas Nacionales (ID: 2)"
[11]: https://www.protectedplanet.net/en "Protected Planet"
[12]: https://api.protectedplanet.net/documentation "ProtectedPlanet API"
[13]: https://www.protectedplanet.net/en/legal "Legal"

