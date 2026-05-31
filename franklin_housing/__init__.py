"""Franklin County (Dublin, OH) housing pull-and-analyze pipeline.

Modules:
  config   - target-area + hygiene-threshold configuration
  client   - paginated ArcGIS REST client (urllib, retry/backoff)
  cache    - SQLite store of raw pulls
  clean    - hygiene/flagging + computed $/sqft and sale-to-assessment ratio
  analyze  - summary stats, time trends, comp-set generation, distributions
  enrich   - optional true-VALID enrichment (default off)
  cli      - command-line entry point
"""

__version__ = "1.0.0"
