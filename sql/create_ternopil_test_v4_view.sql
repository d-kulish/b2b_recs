-- Test view v4: only the last day of data
-- Purpose: Held-out evaluation set with data the model hasn't seen during training
-- v4 changes vs v3:
--   - Added purchase_history ARRAY column: top-50 most recently purchased product IDs per buyer
--   - History computed from TRAINING period (all dates except last day) for point-in-time correctness
--   - Rows and history restricted to top-80% products by cumulative revenue

CREATE OR REPLACE VIEW `b2b-recs.raw_data.ternopil_test_v4` AS

WITH test_data AS (
  SELECT *
  FROM `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil`
  WHERE DATE(date) = (
    SELECT MAX(DATE(date))
    FROM `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil`
  )
),

-- Historical data: all dates EXCEPT the last day (= training period)
historical_data AS (
  SELECT *
  FROM `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil`
  WHERE DATE(date) < (
    SELECT MAX(DATE(date))
    FROM `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil`
  )
),

-- Top 80% products by cumulative revenue (from the full table, all dates)
top_products AS (
  SELECT product_id
  FROM (
    SELECT
      product_id,
      SUM(sales) AS total_revenue,
      SUM(SUM(sales)) OVER () AS grand_total,
      SUM(SUM(sales)) OVER (ORDER BY SUM(sales) DESC) AS running_total
    FROM `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil`
    GROUP BY product_id
  )
  WHERE running_total <= grand_total * 0.8
     OR running_total - total_revenue < grand_total * 0.8
),

-- Unique (customer, product) pairs with most recent purchase date
-- From training period only — point-in-time correctness
-- Only top-80% products
customer_products AS (
  SELECT customer_id, product_id, MAX(date) AS last_purchase_date
  FROM historical_data
  WHERE product_id IN (SELECT product_id FROM top_products)
  GROUP BY customer_id, product_id
),

-- Purchase history per customer: top 50 products by recency
customer_purchase_history AS (
  SELECT
    customer_id,
    ARRAY_AGG(product_id ORDER BY last_purchase_date DESC LIMIT 50) AS purchase_history
  FROM customer_products
  GROUP BY customer_id
)

SELECT
  t.*,
  ch.purchase_history
FROM test_data t
LEFT JOIN customer_purchase_history ch ON t.customer_id = ch.customer_id
WHERE t.product_id IN (SELECT product_id FROM top_products);
