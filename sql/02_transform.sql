CREATE TEMP TABLE clean AS
SELECT DISTINCT
    invoice,
    upper(trim(stock_code))       AS stock_code,
    nullif(trim(description), '') AS description,
    quantity,
    invoice_date,
    price,
    customer_id,
    trim(country)                 AS country,
    invoice LIKE 'C%'             AS is_cancellation
FROM staging.raw_transactions
WHERE invoice ~ '^C?[0-9]+$'
  AND price > 0
  AND quantity <> 0;

INSERT INTO dw.dim_product (stock_code, description, is_service)
SELECT stock_code,
       coalesce(min(description), 'UNKNOWN'),
       stock_code !~ '^[0-9]{5}' AND stock_code !~ '^DCGS'
FROM clean
GROUP BY stock_code;

INSERT INTO dw.dim_customer (customer_id, country, first_order_date, cohort_month)
SELECT customer_id,
       max(country),
       coalesce(min(CASE WHEN NOT is_cancellation THEN invoice_date END), min(invoice_date))::date,
       date_trunc('month', coalesce(min(CASE WHEN NOT is_cancellation THEN invoice_date END), min(invoice_date)))::date
FROM clean
WHERE customer_id IS NOT NULL
GROUP BY customer_id;

INSERT INTO dw.fact_sales
    (invoice, invoice_ts, date_key, customer_id, stock_code, country, quantity, unit_price, is_cancellation)
SELECT invoice, invoice_date, invoice_date::date, customer_id, stock_code, country,
       quantity, price, is_cancellation
FROM clean;
