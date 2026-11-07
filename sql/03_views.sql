CREATE VIEW bi.monthly_kpis AS
SELECT date_trunc('month', f.date_key)::date                                     AS month,
       sum(CASE WHEN NOT f.is_cancellation THEN f.revenue ELSE 0 END)             AS gross_revenue,
       -sum(CASE WHEN f.is_cancellation THEN f.revenue ELSE 0 END)                AS cancelled_revenue,
       sum(f.revenue)                                                             AS net_revenue,
       count(DISTINCT CASE WHEN NOT f.is_cancellation THEN f.invoice END)         AS orders,
       count(DISTINCT CASE WHEN NOT f.is_cancellation THEN f.customer_id END)     AS active_customers,
       round(sum(CASE WHEN NOT f.is_cancellation THEN f.revenue ELSE 0 END)
             / count(DISTINCT CASE WHEN NOT f.is_cancellation THEN f.invoice END), 2) AS avg_order_value,
       round(-sum(CASE WHEN f.is_cancellation THEN f.revenue ELSE 0 END)
             / sum(CASE WHEN NOT f.is_cancellation THEN f.revenue ELSE 0 END), 4)   AS cancellation_rate
FROM dw.fact_sales f
GROUP BY date_trunc('month', f.date_key)::date;

CREATE VIEW bi.new_customers AS
SELECT cohort_month AS month,
       count(*)     AS new_customers
FROM dw.dim_customer
GROUP BY cohort_month;

CREATE VIEW bi.country_summary AS
SELECT f.country,
       sum(f.revenue)                                                             AS net_revenue,
       count(DISTINCT CASE WHEN NOT f.is_cancellation THEN f.invoice END)         AS orders,
       count(DISTINCT f.customer_id)                                              AS customers,
       round(sum(CASE WHEN NOT f.is_cancellation THEN f.revenue ELSE 0 END)
             / count(DISTINCT CASE WHEN NOT f.is_cancellation THEN f.invoice END), 2) AS avg_order_value,
       round(-sum(CASE WHEN f.is_cancellation THEN f.revenue ELSE 0 END)
             / sum(CASE WHEN NOT f.is_cancellation THEN f.revenue ELSE 0 END), 4)   AS cancellation_rate
FROM dw.fact_sales f
GROUP BY f.country;

CREATE VIEW bi.customer_activity AS
SELECT DISTINCT f.customer_id,
       c.cohort_month,
       date_trunc('month', f.date_key)::date AS month
FROM dw.fact_sales f
JOIN dw.dim_customer c ON c.customer_id = f.customer_id
WHERE NOT f.is_cancellation;

CREATE VIEW bi.customer_totals AS
SELECT f.customer_id,
       c.country,
       c.cohort_month,
       max(CASE WHEN NOT f.is_cancellation THEN f.date_key END)                   AS last_order_date,
       count(DISTINCT CASE WHEN NOT f.is_cancellation THEN f.invoice END)         AS frequency,
       sum(f.revenue)                                                             AS monetary
FROM dw.fact_sales f
JOIN dw.dim_customer c ON c.customer_id = f.customer_id
GROUP BY f.customer_id, c.country, c.cohort_month;

CREATE VIEW bi.product_totals AS
SELECT f.stock_code,
       p.description,
       sum(f.revenue)            AS net_revenue,
       sum(f.quantity)           AS net_units,
       count(DISTINCT f.invoice) AS orders
FROM dw.fact_sales f
JOIN dw.dim_product p ON p.stock_code = f.stock_code
WHERE NOT p.is_service
GROUP BY f.stock_code, p.description
HAVING sum(f.revenue) > 0;

CREATE VIEW bi.customer_orders AS
SELECT customer_id,
       invoice,
       min(invoice_ts) AS order_ts
FROM dw.fact_sales
WHERE customer_id IS NOT NULL
  AND NOT is_cancellation
GROUP BY customer_id, invoice;
