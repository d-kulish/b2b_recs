-- Probability-to-buy training view: positives (label=1) + sampled negatives (label=0)
-- Purpose: Binary classification dataset for ranking model predicting purchase probability
--
-- Data source: tfrs_training_examples_v2_Ternopil (all dates except the last day)
-- Positive examples: Deduplicated (customer, product) pairs that had a transaction (label=1)
-- Negative examples: (customer, product) pairs with no transaction, sampled 1:4 per customer (label=0)
-- Negative sampling: Deterministic via FARM_FINGERPRINT (consistent results across queries)
-- Product catalog: All products from the full Ternopil table (not just the training period)

CREATE OR REPLACE VIEW `b2b-recs.raw_data.ternopil_prob_train` AS

WITH train_data AS (
  -- All dates except the last day (same filter as ternopil_train)
  SELECT *
  FROM `b2b-recs.raw_data.tfrs_training_examples_v2_Ternopil`
  WHERE DATE(date) < (
    SELECT MAX(DATE(date))
    FROM `b2b-recs.raw_data.tfrs_training_examples_v2_Ternopil`
  )
),

-- Positive examples: one row per (customer, product) pair, keeping the latest transaction's features
positives AS (
  SELECT
    customer_id, target_group, date, store_id, product_id, sales,
    cust_value, city, art_name, division_desc, stratbuy_domain_desc,
    mge_main_cat_desc, mge_cat_desc, mge_sub_cat_desc, brand_name, segment,
    1 AS label
  FROM (
    SELECT *, ROW_NUMBER() OVER (
      PARTITION BY customer_id, product_id ORDER BY date DESC
    ) AS rn
    FROM train_data
  )
  WHERE rn = 1
),

-- Distinct positive pairs (for exclusion from negative pool)
positive_pairs AS (
  SELECT DISTINCT customer_id, product_id
  FROM positives
),

-- Count of distinct products per customer (for 1:1 negative sampling)
customer_pos_counts AS (
  SELECT customer_id, COUNT(*) AS pos_count
  FROM positive_pairs
  GROUP BY customer_id
),

-- Latest customer context features (used for negative rows)
customer_context AS (
  SELECT customer_id, target_group, date, store_id, cust_value, city, segment
  FROM (
    SELECT customer_id, target_group, date, store_id, cust_value, city, segment,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY date DESC) AS rn
    FROM train_data
  )
  WHERE rn = 1
),

-- Product catalog with metadata (from the full Ternopil table, not just train period)
product_catalog AS (
  SELECT product_id, art_name, division_desc, stratbuy_domain_desc,
         mge_main_cat_desc, mge_cat_desc, mge_sub_cat_desc, brand_name
  FROM (
    SELECT product_id, art_name, division_desc, stratbuy_domain_desc,
           mge_main_cat_desc, mge_cat_desc, mge_sub_cat_desc, brand_name,
           ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY date DESC) AS rn
    FROM `b2b-recs.raw_data.tfrs_training_examples_v2_Ternopil`
  )
  WHERE rn = 1
),

-- Negative candidates: all (customer, product) pairs NOT in positive_pairs
-- Ranked deterministically per customer via FARM_FINGERPRINT for consistent sampling
negative_ranked AS (
  SELECT
    c.customer_id,
    p.product_id,
    ROW_NUMBER() OVER (
      PARTITION BY c.customer_id
      ORDER BY FARM_FINGERPRINT(CONCAT('train_', CAST(c.customer_id AS STRING), '_', CAST(p.product_id AS STRING)))
    ) AS neg_rank
  FROM (SELECT DISTINCT customer_id FROM positive_pairs) c
  CROSS JOIN product_catalog p
  LEFT JOIN positive_pairs pp
    ON c.customer_id = pp.customer_id AND p.product_id = pp.product_id
  WHERE pp.customer_id IS NULL
),

-- Sampled negatives: 1:4 ratio (4 negatives per positive, per customer)
negatives AS (
  SELECT
    cc.customer_id, cc.target_group, cc.date, cc.store_id,
    nr.product_id,
    0.0 AS sales,
    cc.cust_value, cc.city,
    pc.art_name, pc.division_desc, pc.stratbuy_domain_desc,
    pc.mge_main_cat_desc, pc.mge_cat_desc, pc.mge_sub_cat_desc, pc.brand_name,
    cc.segment,
    0 AS label
  FROM negative_ranked nr
  JOIN customer_pos_counts cpc ON nr.customer_id = cpc.customer_id
  JOIN customer_context cc ON nr.customer_id = cc.customer_id
  JOIN product_catalog pc ON nr.product_id = pc.product_id
  WHERE nr.neg_rank <= cpc.pos_count * 4
)

-- Final: positives + negatives
SELECT * FROM positives
UNION ALL
SELECT * FROM negatives;
