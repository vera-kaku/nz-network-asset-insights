# Loading the outputs into Power BI

`assets build` writes a small star schema to `output/`. In Power BI Desktop: **Get data > Text/CSV**, load every file, then set these relationships in Model view (all single direction, many to one):

| From (many) | To (one) | Key |
|---|---|---|
| fact_condition | dim_network | edb_key |
| fact_condition | dim_asset | asset_key |
| fact_age | dim_network, dim_asset | edb_key, asset_key |
| fact_delivery | dim_network | edb_key |
| fact_reliability | dim_network | edb_key |
| priority_latest | dim_network, dim_asset | edb_key, asset_key |

## Suggested measures (DAX)

```DAX
Poor share % =
DIVIDE (
    SUMX ( fact_condition, fact_condition[poor_pct] * fact_condition[quantity] ),
    SUMX ( FILTER ( fact_condition, NOT ISBLANK ( fact_condition[poor_pct] ) ), fact_condition[quantity] )
)

Planned replacement % =
DIVIDE (
    SUMX ( fact_condition, fact_condition[replace_5yr_pct] * fact_condition[quantity] ),
    SUMX ( FILTER ( fact_condition, NOT ISBLANK ( fact_condition[replace_5yr_pct] ) ), fact_condition[quantity] )
)

Coverage gap (pts) = [Poor share %] - [Planned replacement %]

Renewal delivery % =
DIVIDE (
    CALCULATE ( SUM ( fact_delivery[actual] ),
        fact_delivery[spend_type] = "capex",
        CONTAINSSTRING ( fact_delivery[category], "renewal" ) ),
    CALCULATE ( SUM ( fact_delivery[forecast] ),
        fact_delivery[spend_type] = "capex",
        CONTAINSSTRING ( fact_delivery[category], "renewal" ) )
)
```

Suggested pages: a line chart of `Poor share %` by `disc_yr` and `dim_asset[asset_group]`; a bar chart of `Renewal delivery %` by network with a slicer on `reg_period`; a table of `priority_latest` sorted by `priority_rank`.
