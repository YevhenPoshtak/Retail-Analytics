SELECT count(*) AS raw_rows
FROM staging.raw_transactions;

SELECT count(*)                                              AS clean_fact_rows,
       sum(CASE WHEN is_cancellation THEN 1 ELSE 0 END)      AS cancellation_rows,
       sum(CASE WHEN customer_id IS NULL THEN 1 ELSE 0 END)  AS guest_rows
FROM dw.fact_sales;

SELECT p.stock_code, p.description, count(*) AS lines, round(sum(f.revenue), 0) AS net_revenue
FROM dw.fact_sales f
JOIN dw.dim_product p ON p.stock_code = f.stock_code
WHERE p.is_service
GROUP BY p.stock_code, p.description
ORDER BY abs(sum(f.revenue)) DESC
LIMIT 12;

SELECT to_char(m.month, 'YYYY-MM') AS month,
       round(m.net_revenue, 0)     AS net_revenue,
       m.orders,
       m.active_customers,
       n.new_customers,
       m.avg_order_value,
       round(100 * m.cancellation_rate, 1) AS cancellation_pct
FROM bi.monthly_kpis m
LEFT JOIN bi.new_customers n ON n.month = m.month
ORDER BY m.month;

SELECT CASE WHEN date_key < '2010-12-01' THEN 'Y1 (Dec09-Nov10)' ELSE 'Y2 (Dec10-Nov11)' END AS period,
       round(sum(revenue), 0)                                               AS net_revenue,
       count(DISTINCT CASE WHEN NOT is_cancellation THEN invoice END)       AS orders,
       count(DISTINCT customer_id)                                          AS customers,
       round(sum(CASE WHEN NOT is_cancellation THEN revenue ELSE 0 END)
             / count(DISTINCT CASE WHEN NOT is_cancellation THEN invoice END), 2) AS avg_order_value
FROM dw.fact_sales
WHERE date_key < '2011-12-01'
GROUP BY CASE WHEN date_key < '2010-12-01' THEN 'Y1 (Dec09-Nov10)' ELSE 'Y2 (Dec10-Nov11)' END
ORDER BY period;

SELECT stock_code, description, round(net_revenue, 0) AS net_revenue, net_units, orders
FROM bi.product_totals
ORDER BY net_revenue DESC
LIMIT 10;

SELECT country, round(net_revenue, 0) AS net_revenue, orders, customers, avg_order_value,
       round(100 * cancellation_rate, 1) AS cancellation_pct
FROM bi.country_summary
ORDER BY net_revenue DESC
LIMIT 10;

SELECT d.day_of_week, d.day_name,
       count(DISTINCT CASE WHEN extract(hour FROM f.invoice_ts) < 12 THEN f.invoice END)              AS before_12,
       count(DISTINCT CASE WHEN extract(hour FROM f.invoice_ts) BETWEEN 12 AND 14 THEN f.invoice END) AS h12_14,
       count(DISTINCT CASE WHEN extract(hour FROM f.invoice_ts) >= 15 THEN f.invoice END)             AS from_15,
       count(DISTINCT f.invoice)                                                                      AS total_orders
FROM dw.fact_sales f
JOIN dw.dim_date d ON d.date_key = f.date_key
WHERE NOT f.is_cancellation
GROUP BY d.day_of_week, d.day_name
ORDER BY d.day_of_week;
