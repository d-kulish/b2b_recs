-- Test view v3: only the last day of data
-- Purpose: Held-out evaluation set with data the model hasn't seen during training
-- v3: Based on tfrs_training_examples_v3_Ternopil (excludes OTHERS FD / OTHERS NF)
-- Restricted to top 80% products by cumulative revenue

CREATE OR REPLACE VIEW `b2b-recs.raw_data.ternopil_test_v3` AS

WITH top_products AS (
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
)

SELECT *
FROM `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil`
WHERE DATE(date) = (
  SELECT MAX(DATE(date))
  FROM `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil`
)
AND product_id IN (SELECT product_id FROM top_products);
