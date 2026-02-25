-- Probability-to-buy training view v3: positives (label=1) + sampled negatives (label=0)
-- Purpose: Binary classification dataset for ranking model predicting purchase probability
--
-- Data source: tfrs_training_examples_v3_Ternopil (all dates except the last day)
-- Positive examples: Deduplicated (customer, product) pairs that had a transaction (label=1)
-- Negative examples: (customer, product) pairs with no transaction, sampled 1:4 per customer (label=0)
-- Negative sampling: Deterministic via FARM_FINGERPRINT (consistent results across queries)
--
-- v3 changes vs v2:
--   - Based on tfrs_training_examples_v3_Ternopil (excludes OTHERS FD / OTHERS NF)
--   - Product catalog restricted to top 80% products by cumulative revenue

CREATE OR REPLACE VIEW `b2b-recs.raw_data.ternopil_prob_train_v3` AS

WITH train_data AS (
  -- All dates except the last day (same filter as ternopil_train_v3)
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

-- Product catalog with metadata (only top 80% products)
product_catalog AS (
  SELECT product_id, art_name, division_desc, stratbuy_domain_desc,
         mge_main_cat_desc, mge_cat_desc, mge_sub_cat_desc, brand_name
  FROM (
    SELECT product_id, art_name, division_desc, stratbuy_domain_desc,
           mge_main_cat_desc, mge_cat_desc, mge_sub_cat_desc, brand_name,
           ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY date DESC) AS rn
    FROM `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil`
    WHERE product_id IN (SELECT product_id FROM top_products)
  )
  WHERE rn = 1
),

-- Positive examples: one row per (customer, product) pair, keeping the latest transaction's features
-- Filtered to top 80% products only
positives AS (
  SELECT
    customer_id, target_group, date, store_id, product_id, sales,
    cust_value, days_since_last_purchase, cust_order_days_60d, cust_unique_products_60d,
    city, art_name, division_desc, stratbuy_domain_desc,
    mge_main_cat_desc, mge_cat_desc, mge_sub_cat_desc, brand_name, segment,
    1 AS label
  FROM (
    SELECT *, ROW_NUMBER() OVER (
      PARTITION BY customer_id, product_id ORDER BY date DESC
    ) AS rn
    FROM train_data
    WHERE product_id IN (SELECT product_id FROM top_products)
  )
  WHERE rn = 1
),

-- Distinct positive pairs (for exclusion from negative pool)
positive_pairs AS (
  SELECT DISTINCT customer_id, product_id
  FROM positives
),

-- Count of distinct products per customer (for 1:4 negative sampling)
customer_pos_counts AS (
  SELECT customer_id, COUNT(*) AS pos_count
  FROM positive_pairs
  GROUP BY customer_id
),

-- Distinct customer dates with context features (for point-in-time negative sampling)
-- Each customer may have multiple transaction dates with different cust_value
customer_dates AS (
  SELECT customer_id, target_group, date, store_id,
         cust_value, days_since_last_purchase, cust_order_days_60d, cust_unique_products_60d,
         city, segment
  FROM (
    SELECT customer_id, target_group, date, store_id,
           cust_value, days_since_last_purchase, cust_order_days_60d, cust_unique_products_60d,
           city, segment,
           ROW_NUMBER() OVER (
             PARTITION BY customer_id, DATE(date)
             ORDER BY date DESC
           ) AS rn
    FROM train_data
  )
  WHERE rn = 1
),

-- Negative candidates: all (customer, product) pairs NOT in positive_pairs
-- Ranked deterministically per customer via FARM_FINGERPRINT for consistent sampling
-- Only top 80% products are candidates
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
-- Each negative is paired with a random customer date to get point-in-time cust_value
-- This ensures negatives see the same cust_value distribution as positives (no leakage)
negatives AS (
  SELECT
    cd.customer_id, cd.target_group, cd.date, cd.store_id,
    nr.product_id,
    0.0 AS sales,
    cd.cust_value, cd.days_since_last_purchase, cd.cust_order_days_60d, cd.cust_unique_products_60d,
    cd.city,
    pc.art_name, pc.division_desc, pc.stratbuy_domain_desc,
    pc.mge_main_cat_desc, pc.mge_cat_desc, pc.mge_sub_cat_desc, pc.brand_name,
    cd.segment,
    0 AS label
  FROM negative_ranked nr
  JOIN customer_pos_counts cpc ON nr.customer_id = cpc.customer_id
  -- Assign each negative to a customer date deterministically
  JOIN (
    SELECT *, ROW_NUMBER() OVER (
      PARTITION BY customer_id ORDER BY date
    ) AS date_rank,
    COUNT(*) OVER (PARTITION BY customer_id) AS date_count
    FROM customer_dates
  ) cd ON nr.customer_id = cd.customer_id
    AND cd.date_rank = 1 + MOD(nr.neg_rank - 1, cd.date_count)
  JOIN product_catalog pc ON nr.product_id = pc.product_id
  WHERE nr.neg_rank <= cpc.pos_count * 4
)

-- Final: positives + negatives
SELECT * FROM positives
UNION ALL
SELECT * FROM negatives;
