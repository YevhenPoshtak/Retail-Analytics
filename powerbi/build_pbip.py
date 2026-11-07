import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "RetailAnalytics"
MODEL = HERE / f"{NAME}.SemanticModel"
REPORT = HERE / f"{NAME}.Report"
PG_HOST, PG_DB = "localhost", "retail"
BASE_THEME = "CY26SU10"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"

PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]


TABLES = {
    "fact_sales": ("dw", [
        ("invoice", "string", {}),
        ("invoice_ts", "dateTime", {"formatString": "yyyy-mm-dd hh:nn"}),
        ("date_key", "dateTime", {"formatString": "yyyy-mm-dd"}),
        ("customer_id", "int64", {"summarizeBy": "none"}),
        ("stock_code", "string", {}),
        ("country", "string", {}),
        ("quantity", "int64", {}),
        ("unit_price", "double", {}),
        ("revenue", "double", {}),
        ("is_cancellation", "boolean", {}),
    ]),
    "dim_date": ("dw", [
        ("date_key", "dateTime", {"formatString": "yyyy-mm-dd", "isKey": True}),
        ("year", "int64", {"summarizeBy": "none"}),
        ("quarter", "int64", {"summarizeBy": "none"}),
        ("month", "int64", {"summarizeBy": "none"}),
        ("month_start", "dateTime", {"formatString": "yyyy-mm"}),
        ("month_label", "string", {"m": 'Date.ToText(Date.From([month_start]), "yyyy-MM")',
                                   "sortByColumn": "month_start"}),
        ("month_name", "string", {"sortByColumn": "month"}),
        ("iso_week", "int64", {"summarizeBy": "none"}),
        ("day_of_week", "int64", {"summarizeBy": "none"}),
        ("day_name", "string", {"sortByColumn": "day_of_week"}),
        ("is_weekend", "boolean", {}),
    ]),
    "dim_product": ("dw", [
        ("stock_code", "string", {}),
        ("description", "string", {}),
        ("is_service", "boolean", {}),
    ]),
    "dim_customer": ("dw", [
        ("customer_id", "int64", {"summarizeBy": "none"}),
        ("country", "string", {}),
        ("first_order_date", "dateTime", {"formatString": "yyyy-mm-dd"}),
        ("cohort_month", "dateTime", {"formatString": "yyyy-mm"}),
    ]),
    "cohort_retention": ("bi", [
        ("cohort_month", "dateTime", {"formatString": "yyyy-mm"}),
        ("cohort", "string", {"m": 'Date.ToText(Date.From([cohort_month]), "yyyy-MM")',
                              "sortByColumn": "cohort_month"}),
        ("month_number", "int64", {"summarizeBy": "none"}),
        ("active_customers", "int64", {}),
        ("cohort_size", "int64", {}),
        ("retention_rate", "double", {"formatString": "0.0%"}),
    ]),
    "customer_rfm": ("bi", [
        ("customer_id", "int64", {"summarizeBy": "none"}),
        ("recency_days", "int64", {}),
        ("frequency", "int64", {}),
        ("monetary", "double", {"formatString": "\\£#,0"}),
        ("r_score", "int64", {"summarizeBy": "none"}),
        ("f_score", "int64", {"summarizeBy": "none"}),
        ("m_score", "int64", {"summarizeBy": "none"}),
        ("country", "string", {}),
        ("segment", "string", {}),
    ]),
    "product_abc": ("bi", [
        ("stock_code", "string", {}),
        ("description", "string", {}),
        ("net_revenue", "double", {"formatString": "\\£#,0", "summarizeBy": "none"}),
        ("net_units", "int64", {"summarizeBy": "none"}),
        ("orders", "int64", {"summarizeBy": "none"}),
        ("revenue_rank", "int64", {"summarizeBy": "none"}),
        ("cumulative_share", "double", {"formatString": "0.0%", "summarizeBy": "none"}),
        ("abc_class", "string", {}),
    ]),
}

GBP, PCT, INT = "\\£#,0", "0.0%", "#,0"
MEASURES = {
    "fact_sales": [
        ("Net Revenue", "SUM ( fact_sales[revenue] )", GBP),
        ("Gross Revenue", "CALCULATE ( [Net Revenue], fact_sales[is_cancellation] = FALSE () )", GBP),
        ("Cancelled Revenue", "- CALCULATE ( [Net Revenue], fact_sales[is_cancellation] = TRUE () )", GBP),
        ("Cancellation Rate", "DIVIDE ( [Cancelled Revenue], [Gross Revenue] )", PCT),
        ("Orders", "CALCULATE ( DISTINCTCOUNT ( fact_sales[invoice] ), fact_sales[is_cancellation] = FALSE () )", INT),
        ("Customers", "CALCULATE ( DISTINCTCOUNT ( fact_sales[customer_id] ), fact_sales[is_cancellation] = FALSE (), NOT ISBLANK ( fact_sales[customer_id] ) )", INT),
        ("Avg Order Value", "DIVIDE ( [Gross Revenue], [Orders] )", "\\£#,0.00"),
        ("Revenue per Customer", "DIVIDE ( CALCULATE ( [Net Revenue], NOT ISBLANK ( fact_sales[customer_id] ) ), [Customers] )", GBP),
        ("Net Revenue PY", "CALCULATE ( [Net Revenue], SAMEPERIODLASTYEAR ( dim_date[date_key] ) )", GBP),
        ("Net Revenue YoY %", "DIVIDE ( [Net Revenue] - [Net Revenue PY], [Net Revenue PY] )", PCT),
        ("Guest Revenue Share", "DIVIDE ( CALCULATE ( [Net Revenue], ISBLANK ( fact_sales[customer_id] ) ), [Net Revenue] )", PCT),
    ],
    "cohort_retention": [("Retention Rate", "AVERAGE ( cohort_retention[retention_rate] )", "0%")],
    "customer_rfm": [
        ("RFM Customers", "COUNTROWS ( customer_rfm )", INT),
        ("RFM Revenue", "SUM ( customer_rfm[monetary] )", GBP),
        ("RFM Recency Days", "AVERAGE ( customer_rfm[recency_days] )", "#,0"),
        ("RFM Revenue log10", "LOG10 ( [RFM Revenue] )", "0.0"),
    ],
    "product_abc": [
        ("ABC Revenue", "SUM ( product_abc[net_revenue] )", GBP),
        ("ABC Products", "COUNTROWS ( product_abc )", INT),
    ],
}

RELATIONSHIPS = [
    ("fact_sales", "date_key", "dim_date", "date_key"),
    ("fact_sales", "stock_code", "dim_product", "stock_code"),
    ("fact_sales", "customer_id", "dim_customer", "customer_id"),
]


def q(name: str) -> str:
    return f"'{name}'" if any(c in name for c in " %.-") else name


def table_tmdl(table: str, schema: str, columns) -> str:
    lines = [f"table {table}"]
    if table == "dim_date":
        lines.append("\tdataCategory: Time")
    lines.append("")
    for name, expr, fmt in MEASURES.get(table, []):
        lines += [f"\tmeasure {q(name)} = {expr}", f"\t\tformatString: {fmt}", ""]
    for col, dtype, extra in columns:
        lines.append(f"\tcolumn {col}")
        lines.append(f"\t\tdataType: {dtype}")
        if extra.get("isKey"):
            lines.append("\t\tisKey")
        if "formatString" in extra:
            lines.append(f"\t\tformatString: {extra['formatString']}")
        summarize = extra.get("summarizeBy", "sum" if dtype in ("int64", "double") else "none")
        lines.append(f"\t\tsummarizeBy: {summarize}")
        lines.append(f"\t\tsourceColumn: {col}")
        if "sortByColumn" in extra:
            lines.append(f"\t\tsortByColumn: {extra['sortByColumn']}")
        lines.append("")
    cols = ", ".join(f'"{c}"' for c, _, e in columns if "m" not in e)
    steps = [f'Source = PostgreSQL.Database("{PG_HOST}", "{PG_DB}")',
             f'Data = Source{{[Schema="{schema}", Item="{table}"]}}[Data]',
             f"Result = Table.SelectColumns(Data, {{{cols}}})"]
    for c, _, e in columns:
        if "m" in e:
            steps.append(f'Result_{c} = Table.AddColumn({steps[-1].split(" = ")[0]}, "{c}", each {e["m"]}, type text)')
    last = steps[-1].split(" = ")[0]
    lines += [f"\tpartition {table} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet"]
    lines += [f"\t\t\t\t    {s}," for s in steps[:-1]] + [f"\t\t\t\t    {steps[-1]}"]
    lines += ["\t\t\t\tin", f"\t\t\t\t    {last}", ""]
    return "\n".join(lines)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, obj) -> None:
    write(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def build_model() -> None:
    d = MODEL / "definition"
    write_json(MODEL / "definition.pbism", {
        "$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {}})
    write(d / "database.tmdl", "database\n\tcompatibilityLevel: 1600\n")
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tsourceQueryCulture: en-US", "\tdataAccessOptions", "\t\tlegacyRedirects",
             "\t\treturnErrorValuesAsNull", "",
             "annotation __PBI_TimeIntelligenceEnabled = 0", ""]
    model += [f"ref table {t}" for t in TABLES] + [""]
    write(d / "model.tmdl", "\n".join(model))
    rel = []
    for i, (ft, fc, tt, tc) in enumerate(RELATIONSHIPS, 1):
        rel += [f"relationship rel_{ft}_{tt}", f"\tfromColumn: {ft}.{fc}", f"\ttoColumn: {tt}.{tc}", ""]
    write(d / "relationships.tmdl", "\n".join(rel))
    for table, (schema, cols) in TABLES.items():
        write(d / "tables" / f"{table}.tmdl", table_tmdl(table, schema, cols))


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def col(entity, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def msr(entity, prop):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def proj(field):
    kind = "Column" if "Column" in field else "Measure"
    entity = field[kind]["Expression"]["SourceRef"]["Entity"]
    prop = field[kind]["Property"]
    return {"field": field, "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}


CHARTS = {"lineChart", "clusteredBarChart", "clusteredColumnChart", "scatterChart"}


def visual(name, vtype, pos, roles, title=None, sort=None, objects=None, filters=None):
    x, y, w, h = pos
    objects = dict(objects or {})
    if vtype in CHARTS:
        for axis in ("categoryAxis", "valueAxis"):
            props = objects.get(axis, [{"properties": {}}])[0]["properties"]
            props["showAxisTitle"] = lit("false")
            objects[axis] = [{"properties": props}]
    v = {"visualType": vtype,
         "query": {"queryState": {r: {"projections": [proj(f) for f in fs]} for r, fs in roles.items()}},
         "drillFilterOtherVisuals": True}
    if sort:
        field, direction = sort
        v["query"]["sortDefinition"] = {"sort": [{"field": field, "direction": direction}], "isDefaultSort": True}
    if objects:
        v["objects"] = objects
    if title:
        v["visualContainerObjects"] = {"title": [{"properties": {
            "show": lit("true"), "text": lit(f"'{title}'"), "fontSize": lit("12D"), "bold": lit("true")}}]}
    c = {"$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.4.0/schema.json",
         "name": name, "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0},
         "visual": v}
    if filters:
        c["filterConfig"] = {"filters": filters}
    return c


def top_n_filter(name, entity, column, measure, n):
    src = {"SourceRef": {"Source": "s"}}
    return {
        "name": name, "field": col(entity, column), "type": "TopN",
        "filter": {"Version": 2, "From": [
            {"Name": "subquery", "Expression": {"Subquery": {"Query": {
                "Version": 2, "From": [{"Name": "s", "Entity": entity, "Type": 0}],
                "Select": [{"Column": {"Expression": src, "Property": column}, "Name": "field"}],
                "OrderBy": [{"Direction": 2, "Expression": {"Measure": {"Expression": src, "Property": measure}}}],
                "Top": n}}}, "Type": 2},
            {"Name": "t", "Entity": entity, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}],
                "Table": {"SourceRef": {"Source": "subquery"}}}}}]}}


def range_filter(name, entity, column, low=None, high=None):
    def cmp(kind, value):
        return {"Comparison": {
            "ComparisonKind": kind,
            "Left": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}},
            "Right": {"Literal": {"Value": f"{value}L"}}}}
    conds = ([cmp(2, low)] if low is not None else []) + ([cmp(4, high)] if high is not None else [])
    cond = conds[0] if len(conds) == 1 else {"And": {"Left": conds[0], "Right": conds[1]}}
    return {
        "name": name, "field": col(entity, column), "type": "Advanced",
        "filter": {"Version": 2, "From": [{"Name": "t", "Entity": entity, "Type": 0}],
                   "Where": [{"Condition": cond}]}}


def heatmap_objects(measure_field, query_ref):
    return {"values": [{"properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {
        "Input": measure_field,
        "FillRule": {"linearGradient2": {
            "min": {"color": {"Literal": {"Value": "'#ffffff'"}}},
            "max": {"color": {"Literal": {"Value": f"'{PALETTE[0]}'"}}},
            "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'asZero'"}}}}}}}}}}},
        "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": query_ref}}]}


F = "fact_sales"


def overview():
    cards = ["Net Revenue", "Orders", "Customers", "Avg Order Value", "Cancellation Rate"]
    dropdown = {"data": [{"properties": {"mode": lit("'Dropdown'")}}]}
    vs = [visual(f"card_{i}", "card", (16 + i * 252, 16, 240, 104), {"Values": [msr(F, m)]})
          for i, m in enumerate(cards)]
    vs.append(visual("revenue_trend", "lineChart", (16, 136, 820, 300),
                     {"Category": [col("dim_date", "month_label")],
                      "Y": [msr(F, "Net Revenue"), msr(F, "Net Revenue PY")]},
                     title="Net revenue by month vs previous year",
                     sort=(col("dim_date", "month_label"), "Ascending")))
    vs.append(visual("year_slicer", "slicer", (852, 136, 200, 100), {"Values": [col("dim_date", "year")]},
                     title="Year", objects=dropdown))
    vs.append(visual("country_slicer", "slicer", (1064, 136, 200, 100), {"Values": [col(F, "country")]},
                     title="Country", objects=dropdown))
    vs.append(visual("top_countries", "clusteredBarChart", (852, 252, 412, 452),
                     {"Category": [col(F, "country")], "Y": [msr(F, "Net Revenue")]},
                     title="Top 10 countries by net revenue",
                     sort=(msr(F, "Net Revenue"), "Descending"),
                     filters=[top_n_filter("top10_countries", F, "country", "Net Revenue", 10)]))
    vs.append(visual("orders_by_weekday", "clusteredColumnChart", (16, 452, 820, 252),
                     {"Category": [col("dim_date", "day_name")], "Y": [msr(F, "Orders")]},
                     title="Orders by day of week",
                     sort=(col("dim_date", "day_name"), "Ascending")))
    return "overview", "Overview", vs


def customers():
    r = "cohort_retention"
    rate = msr(r, "Retention Rate")
    heat = heatmap_objects(rate, f"{r}.Retention Rate")
    heat["subTotals"] = [{"properties": {"rowSubtotals": lit("false"), "columnSubtotals": lit("false")}}]
    vs = [visual("cohort_heatmap", "pivotTable", (16, 16, 1248, 400),
                 {"Rows": [col(r, "cohort")], "Columns": [col(r, "month_number")], "Values": [rate]},
                 title="Cohort retention: share of each monthly cohort active 1-12 months after the first order",
                 objects=heat,
                 filters=[range_filter("months_1_12", r, "month_number", 1, 12)])]
    s = "customer_rfm"
    vs.append(visual("rfm_customers", "clusteredBarChart", (16, 432, 400, 272),
                     {"Category": [col(s, "segment")], "Y": [msr(s, "RFM Customers")]},
                     title="RFM segments: customers", sort=(msr(s, "RFM Customers"), "Descending")))
    vs.append(visual("rfm_revenue", "clusteredBarChart", (432, 432, 400, 272),
                     {"Category": [col(s, "segment")], "Y": [msr(s, "RFM Revenue")]},
                     title="RFM segments: revenue", sort=(msr(s, "RFM Revenue"), "Descending")))
    vs.append(visual("rfm_scatter", "scatterChart", (848, 432, 416, 272),
                     {"Category": [col(s, "customer_id")], "Series": [col(s, "segment")],
                      "X": [msr(s, "RFM Recency Days")], "Y": [msr(s, "RFM Revenue log10")]},
                     title="Days since last order (x) vs log10 revenue per customer (y)"))
    return "customers", "Customers", vs


def products():
    p = "product_abc"
    vs = [visual("top_products", "clusteredBarChart", (16, 16, 620, 400),
                 {"Category": [col(p, "description")], "Y": [msr(p, "ABC Revenue")]},
                 title="Top 10 products by net revenue", sort=(msr(p, "ABC Revenue"), "Descending"),
                 filters=[range_filter("top10_products", p, "revenue_rank", high=10)])]
    vs.append(visual("abc_revenue", "donutChart", (652, 16, 300, 400),
                     {"Category": [col(p, "abc_class")], "Y": [msr(p, "ABC Revenue")]},
                     title="Revenue by ABC class"))
    vs.append(visual("abc_products", "donutChart", (964, 16, 300, 400),
                     {"Category": [col(p, "abc_class")], "Y": [msr(p, "ABC Products")]},
                     title="Products by ABC class"))
    widths = [("revenue_rank", 110), ("description", 480), ("net_revenue", 170),
              ("net_units", 150), ("orders", 130), ("abc_class", 130)]
    vs.append(visual("product_table", "tableEx", (16, 432, 1248, 272),
                     {"Values": [col(p, c) for c, _ in widths]},
                     title="Product ranking", sort=(col(p, "revenue_rank"), "Ascending"),
                     objects={"columnWidth": [
                         {"properties": {"value": lit(f"{w}D")}, "selector": {"metadata": f"{p}.{c}"}}
                         for c, w in widths]}))
    return "products", "Products", vs


def build_report() -> None:
    d = REPORT / "definition"
    version = {"visual": "2.4.0", "report": "3.0.0", "page": "2.0.0"}
    write_json(REPORT / "definition.pbir", {
        "$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    write_json(d / "version.json", {
        "$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    write_json(d / "report.json", {
        "$schema": f"{SCHEMA}/item/report/definition/report/3.0.0/schema.json",
        "themeCollection": {
            "baseTheme": {"name": BASE_THEME, "reportVersionAtImport": version, "type": "SharedResources"},
            "customTheme": {"name": f"{NAME}.json", "reportVersionAtImport": version, "type": "RegisteredResources"}},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": BASE_THEME, "path": f"BaseThemes/{BASE_THEME}.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": f"{NAME}.json", "path": f"{NAME}.json", "type": "CustomTheme"}]}]})
    theme_src = next(Path("C:/Program Files/WindowsApps").glob(
        f"Microsoft.MicrosoftPowerBIDesktop_*/bin/WebView2Resources/minerva/sharedresources/BaseThemes/{BASE_THEME}.json"))
    base_dst = REPORT / "StaticResources" / "SharedResources" / "BaseThemes" / f"{BASE_THEME}.json"
    base_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(theme_src, base_dst)
    write_json(REPORT / "StaticResources" / "RegisteredResources" / f"{NAME}.json", {
        "name": NAME, "dataColors": PALETTE, "foreground": "#0b0b0b", "foregroundNeutralSecondary": "#52514e",
        "background": "#ffffff", "tableAccent": PALETTE[0]})

    pages = [overview(), customers(), products()]
    write_json(d / "pages" / "pages.json", {
        "$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p[0] for p in pages], "activePageName": pages[0][0]})
    for name, display, vs in pages:
        write_json(d / "pages" / name / "page.json", {
            "$schema": f"{SCHEMA}/item/report/definition/page/2.0.0/schema.json",
            "name": name, "displayName": display, "displayOption": "FitToPage", "height": 720, "width": 1280})
        for i, v in enumerate(vs):
            v["position"]["z"] = i
            v["position"]["tabOrder"] = i
            write_json(d / "pages" / name / "visuals" / v["name"] / "visual.json", v)


def main() -> None:
    for p in (MODEL, REPORT):
        if p.exists():
            shutil.rmtree(p)
    build_model()
    build_report()
    write_json(HERE / f"{NAME}.pbip", {
        "$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}], "settings": {"enableAutoRecovery": True}})
    print(f"written {HERE / (NAME + '.pbip')}")


if __name__ == "__main__":
    main()
