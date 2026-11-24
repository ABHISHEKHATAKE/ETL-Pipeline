-- Analytics queries on the warehouse. Run with:  make psql < sql/analytics.sql
-- (or paste individual queries into any SQL client)

-- 1. Monthly revenue with month-over-month growth  (CTE + LAG window function)
WITH monthly AS (
    SELECT d.year, d.month, SUM(f.net_amount) AS revenue
    FROM fact_sales f JOIN dim_date d USING (date_key)
    GROUP BY d.year, d.month
)
SELECT year, month, ROUND(revenue, 2) AS revenue,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY year, month))
             / NULLIF(LAG(revenue) OVER (ORDER BY year, month), 0), 1) AS mom_growth_pct
FROM monthly
ORDER BY year, month;

-- 2. Top 3 products by revenue in every category  (RANK per partition)
SELECT category, product_name, revenue, rnk FROM (
    SELECT p.category, p.product_name, ROUND(SUM(f.net_amount), 2) AS revenue,
           RANK() OVER (PARTITION BY p.category ORDER BY SUM(f.net_amount) DESC) AS rnk
    FROM fact_sales f JOIN dim_product p USING (product_key)
    GROUP BY p.category, p.product_name
) t
WHERE rnk <= 3
ORDER BY category, rnk;

-- 3. Each customer's running total and order sequence  (SUM OVER + ROW_NUMBER)
SELECT c.customer_id, f.order_id, d.full_date, f.net_amount,
       SUM(f.net_amount) OVER (PARTITION BY f.customer_key
                               ORDER BY d.full_date, f.order_id, f.order_line) AS running_total,
       ROW_NUMBER() OVER (PARTITION BY f.customer_key
                          ORDER BY d.full_date, f.order_id, f.order_line) AS line_seq
FROM fact_sales f
JOIN dim_customer c USING (customer_key)
JOIN dim_date d USING (date_key)
WHERE c.customer_id = 'C00001'
ORDER BY d.full_date, f.order_id, f.order_line;

-- 4. Revenue share by country  (window over the whole result)
SELECT c.country, ROUND(SUM(f.net_amount), 2) AS revenue,
       ROUND(100.0 * SUM(f.net_amount) / SUM(SUM(f.net_amount)) OVER (), 1) AS share_pct
FROM fact_sales f JOIN dim_customer c USING (customer_key)
GROUP BY c.country
ORDER BY revenue DESC;

-- 5. 7-day moving average of daily revenue  (frame clause)
WITH daily AS (
    SELECT d.full_date, SUM(f.net_amount) AS revenue
    FROM fact_sales f JOIN dim_date d USING (date_key)
    GROUP BY d.full_date
)
SELECT full_date, ROUND(revenue, 2) AS revenue,
       ROUND(AVG(revenue) OVER (ORDER BY full_date
             ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS moving_avg_7d
FROM daily ORDER BY full_date LIMIT 30;

-- 6. Weekend vs weekday sales
SELECT CASE WHEN d.is_weekend THEN 'weekend' ELSE 'weekday' END AS day_type,
       COUNT(*) AS lines, ROUND(AVG(f.net_amount), 2) AS avg_line_value
FROM fact_sales f JOIN dim_date d USING (date_key)
GROUP BY d.is_weekend;

-- ------------------------------------------------------- data quality checks
-- 7. Why rows were rejected in the latest successful run
SELECT reject_reason, COUNT(*) AS rows
FROM rejected_records
WHERE run_id = (SELECT run_id FROM etl_run_log WHERE status = 'success'
                ORDER BY finished_at DESC LIMIT 1)
GROUP BY reject_reason ORDER BY rows DESC;

-- 8. Duplicate check on the fact grain (must return zero rows)
SELECT order_id, order_line, COUNT(*) FROM fact_sales
GROUP BY order_id, order_line HAVING COUNT(*) > 1;

-- 9. Run history
SELECT run_id, status, rows_extracted, rows_valid, rows_rejected, fact_rows_added,
       ROUND(EXTRACT(EPOCH FROM (finished_at - started_at))) AS seconds
FROM etl_run_log ORDER BY started_at DESC LIMIT 10;
