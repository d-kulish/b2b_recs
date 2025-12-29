WITH filtered_data AS (

    SELECT
        tfrs_training_examples.customer_id,
        tfrs_training_examples.date,
        tfrs_training_examples.product_id,
        tfrs_training_examples.sales,
        tfrs_training_examples.cust_value,
        tfrs_training_examples.city,
        tfrs_training_examples.division_desc,
        tfrs_training_examples.mge_cat_desc
    FROM `b2b-recs.raw_data.tfrs_training_examples` AS tfrs_training_examples

    WHERE tfrs_training_examples.date >= TIMESTAMP_SUB((SELECT MAX(date) FROM `b2b-recs.raw_data.tfrs_training_examples`), INTERVAL 60 DAY) AND
        tfrs_training_examples.city IN ('VINNYTSYA')
),
top_products AS (

    SELECT product_id as product_id
    FROM (
        SELECT
            product_id as product_id,
            SUM(sales) as total_revenue,
            SUM(SUM(sales)) OVER () as grand_total,
            SUM(SUM(sales)) OVER (ORDER BY SUM(sales) DESC) as running_total
        FROM filtered_data
        GROUP BY product_id
    )
    WHERE running_total <= grand_total * 0.8
       OR running_total - total_revenue < grand_total * 0.8
),
filtered_customers_0 AS (

    SELECT customer_id as customer_id
    FROM filtered_data
    GROUP BY customer_id
    HAVING COUNT(*) > 2
)
SELECT
  customer_id,
  date,
  product_id,
  sales,
  cust_value,
  city,
  division_desc,
  mge_cat_desc
FROM filtered_data
WHERE
  product_id IN (SELECT product_id FROM top_products) AND
  customer_id IN (SELECT customer_id FROM filtered_customers_0)