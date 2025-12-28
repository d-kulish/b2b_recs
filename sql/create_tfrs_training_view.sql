-- Create view for TFRS training examples
-- This view combines invoices, stores, products, and segments data
-- Filtered to: positive sell_val_nsp AND flag_cust_target_group = 'SCO'

CREATE OR REPLACE VIEW `b2b-recs.raw_data.tfrs_training_examples` AS
WITH filtered_invoices AS (
  -- Filter invoices: positive sell_val_nsp and SCO target group only
  SELECT
    cust_person_id,
    flag_cust_target_group,
    TIMESTAMP(date_of_day) AS date_of_day,
    store_id,
    CAST(art_no AS INT64) * 1000000 + CAST(var_tu_key AS INT64) AS product_id,
    SAFE_CAST(sell_val_nsp AS FLOAT64) AS sell_val_nsp
  FROM `b2b-recs.raw_data.old_csv_invoices`
  WHERE SAFE_CAST(sell_val_nsp AS FLOAT64) > 0
    AND flag_cust_target_group = 'SCO'
),

products_with_id AS (
  -- Create product_id for products table using same formula
  SELECT DISTINCT
    CAST(art_no AS INT64) * 1000000 + CAST(var_tu_key AS INT64) AS product_id,
    division_desc,
    mge_cat_desc
  FROM `b2b-recs.raw_data.test_articles`
),

-- Pre-aggregate daily totals per customer for efficient rolling sum
daily_customer_totals AS (
  SELECT
    cust_person_id,
    DATE(date_of_day) AS txn_date,
    SUM(sell_val_nsp) AS daily_total
  FROM filtered_invoices
  GROUP BY cust_person_id, DATE(date_of_day)
)

SELECT
  i.cust_person_id AS customer_id,
  i.flag_cust_target_group AS target_group,
  i.date_of_day AS date,
  i.store_id,
  i.product_id,
  i.sell_val_nsp AS sales,

  -- Rolling 60-day sum of sell_val_nsp for the customer (excluding current day)
  COALESCE(
    (
      SELECT SUM(dct.daily_total)
      FROM daily_customer_totals dct
      WHERE dct.cust_person_id = i.cust_person_id
        AND dct.txn_date >= DATE_SUB(DATE(i.date_of_day), INTERVAL 20 DAY)
        AND dct.txn_date < DATE(i.date_of_day)
    ),
    0
  ) AS cust_value,

  -- Store context
  s.city,

  -- Product context
  p.division_desc,
  p.mge_cat_desc,

  -- Customer segment context
  seg.segment_group AS segment

FROM filtered_invoices i

-- Join with stores for city
LEFT JOIN `b2b-recs.raw_data.old_csv_stores` s
  ON i.store_id = s.store_id

-- Join with products for division and category
LEFT JOIN products_with_id p
  ON i.product_id = p.product_id

-- Join with segments for segment_group
-- Note: Using latest segment per customer if multiple periods exist
LEFT JOIN (
  SELECT
    cust_person_id,
    segment_group,
    ROW_NUMBER() OVER (PARTITION BY cust_person_id ORDER BY data_period DESC) AS rn
  FROM `b2b-recs.raw_data.cust_segment`
) seg
  ON i.cust_person_id = seg.cust_person_id
  AND seg.rn = 1
;
