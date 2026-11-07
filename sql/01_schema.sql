DROP SCHEMA IF EXISTS bi CASCADE;
DROP SCHEMA IF EXISTS dw CASCADE;
DROP SCHEMA IF EXISTS staging CASCADE;

CREATE SCHEMA staging;
CREATE SCHEMA dw;
CREATE SCHEMA bi;

CREATE TABLE staging.raw_transactions (
    invoice      text,
    stock_code   text,
    description  text,
    quantity     integer,
    invoice_date timestamp,
    price        numeric(12, 3),
    customer_id  integer,
    country      text
);

CREATE TABLE dw.dim_date (
    date_key     date PRIMARY KEY,
    year         smallint NOT NULL,
    quarter      smallint NOT NULL,
    month        smallint NOT NULL,
    month_start  date     NOT NULL,
    month_name   text     NOT NULL,
    iso_week     smallint NOT NULL,
    day_of_week  smallint NOT NULL,
    day_name     text     NOT NULL,
    is_weekend   boolean  NOT NULL
);

CREATE TABLE dw.dim_product (
    stock_code  text PRIMARY KEY,
    description text    NOT NULL,
    is_service  boolean NOT NULL
);

CREATE TABLE dw.dim_customer (
    customer_id      integer PRIMARY KEY,
    country          text NOT NULL,
    first_order_date date NOT NULL,
    cohort_month     date NOT NULL
);

CREATE TABLE dw.fact_sales (
    line_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice         text      NOT NULL,
    invoice_ts      timestamp NOT NULL,
    date_key        date      NOT NULL REFERENCES dw.dim_date,
    customer_id     integer            REFERENCES dw.dim_customer,
    stock_code      text      NOT NULL REFERENCES dw.dim_product,
    country         text      NOT NULL,
    quantity        integer   NOT NULL,
    unit_price      numeric(12, 3) NOT NULL,
    revenue         numeric(14, 2) GENERATED ALWAYS AS (quantity * unit_price) STORED,
    is_cancellation boolean   NOT NULL
);

CREATE TABLE bi.cohort_retention (
    cohort_month     date    NOT NULL,
    month_number     integer NOT NULL,
    active_customers integer NOT NULL,
    cohort_size      integer NOT NULL,
    retention_rate   numeric(6, 4) NOT NULL,
    PRIMARY KEY (cohort_month, month_number)
);

CREATE TABLE bi.customer_rfm (
    customer_id  integer PRIMARY KEY,
    recency_days integer NOT NULL,
    frequency    integer NOT NULL,
    monetary     numeric(14, 2) NOT NULL,
    r_score      smallint NOT NULL,
    f_score      smallint NOT NULL,
    m_score      smallint NOT NULL,
    country      text NOT NULL,
    cohort_month date NOT NULL,
    segment      text NOT NULL
);

CREATE TABLE bi.product_abc (
    stock_code       text PRIMARY KEY,
    description      text NOT NULL,
    net_revenue      numeric(14, 2) NOT NULL,
    net_units        integer NOT NULL,
    orders           integer NOT NULL,
    revenue_rank     integer NOT NULL,
    cumulative_share numeric(8, 6) NOT NULL,
    abc_class        char(1) NOT NULL
);
