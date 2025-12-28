-- ============================================================================
-- CHERNIGIV DATASET VERIFICATION TEST
-- ============================================================================
-- Purpose: Verify whether the Dataset Wizard generates correct configurations
--
-- This test compares:
-- 1. Wizard-generated query behavior (top products calculated globally)
-- 2. Alternative interpretation (top products calculated per filtered city)
-- ============================================================================

-- ============================================================================
-- TEST 1: Understand the data context (run this first)
-- ============================================================================

-- 1.1: How many rows and cities are in the last 60 days?
WITH filtered_data AS (
    SELECT *
    FROM `b2b-recs.raw_data.tfrs_training_examples`
    WHERE date >= TIMESTAMP_SUB((SELECT MAX(date) FROM `b2b-recs.raw_data.tfrs_training_examples`), INTERVAL 60 DAY)
)
SELECT
    'all_cities' as scope,
    COUNT(*) as total_rows,
    COUNT(DISTINCT city) as unique_cities,
    COUNT(DISTINCT product_id) as unique_products,
    COUNT(DISTINCT customer_id) as unique_customers,
    SUM(sales) as total_sales
FROM filtered_data
UNION ALL
SELECT
    'chernigiv_only' as scope,
    COUNT(*) as total_rows,
    1 as unique_cities,
    COUNT(DISTINCT product_id) as unique_products,
    COUNT(DISTINCT customer_id) as unique_customers,
    SUM(sales) as total_sales
FROM filtered_data
WHERE city = 'CHERNIGIV';

-- ============================================================================
-- TEST 2: Top 80% Products - GLOBAL vs CHERNIGIV-ONLY calculation
-- ============================================================================

-- 2.1: Method A - Global top products (what wizard generates)
-- Top products calculated from ALL cities, then filter by CHERNIGIV
WITH filtered_data AS (
    SELECT *
    FROM `b2b-recs.raw_data.tfrs_training_examples`
    WHERE date >= TIMESTAMP_SUB((SELECT MAX(date) FROM `b2b-recs.raw_data.tfrs_training_examples`), INTERVAL 60 DAY)
),
top_products_global AS (
    SELECT product_id
    FROM (
        SELECT
            product_id,
            SUM(sales) as total_revenue,
            SUM(SUM(sales)) OVER () as grand_total,
            SUM(SUM(sales)) OVER (ORDER BY SUM(sales) DESC) as running_total
        FROM filtered_data
        GROUP BY product_id
    )
    WHERE running_total <= grand_total * 0.8
       OR running_total - total_revenue < grand_total * 0.8
)
SELECT
    'global_top_products' as method,
    COUNT(DISTINCT product_id) as products_in_top80,
    (SELECT COUNT(*) FROM top_products_global) as total_top80_products_globally
FROM top_products_global;

-- 2.2: Method B - CHERNIGIV-only top products
-- Top products calculated from CHERNIGIV data only
WITH filtered_data_chernigiv AS (
    SELECT *
    FROM `b2b-recs.raw_data.tfrs_training_examples`
    WHERE date >= TIMESTAMP_SUB((SELECT MAX(date) FROM `b2b-recs.raw_data.tfrs_training_examples`), INTERVAL 60 DAY)
      AND city = 'CHERNIGIV'
),
top_products_chernigiv AS (
    SELECT product_id
    FROM (
        SELECT
            product_id,
            SUM(sales) as total_revenue,
            SUM(SUM(sales)) OVER () as grand_total,
            SUM(SUM(sales)) OVER (ORDER BY SUM(sales) DESC) as running_total
        FROM filtered_data_chernigiv
        GROUP BY product_id
    )
    WHERE running_total <= grand_total * 0.8
       OR running_total - total_revenue < grand_total * 0.8
)
SELECT
    'chernigiv_top_products' as method,
    COUNT(DISTINCT product_id) as products_in_top80
FROM top_products_chernigiv;

-- ============================================================================
-- TEST 3: Compare final row counts between two approaches
-- ============================================================================

-- 3.1: Wizard approach - global top products, then filter by city
WITH filtered_data AS (
    SELECT *
    FROM `b2b-recs.raw_data.tfrs_training_examples`
    WHERE date >= TIMESTAMP_SUB((SELECT MAX(date) FROM `b2b-recs.raw_data.tfrs_training_examples`), INTERVAL 60 DAY)
),
top_products_global AS (
    SELECT product_id
    FROM (
        SELECT
            product_id,
            SUM(sales) as total_revenue,
            SUM(SUM(sales)) OVER () as grand_total,
            SUM(SUM(sales)) OVER (ORDER BY SUM(sales) DESC) as running_total
        FROM filtered_data
        GROUP BY product_id
    )
    WHERE running_total <= grand_total * 0.8
       OR running_total - total_revenue < grand_total * 0.8
)
SELECT
    'method_A_wizard_global_then_city' as approach,
    COUNT(*) as total_rows,
    COUNT(DISTINCT product_id) as unique_products,
    COUNT(DISTINCT customer_id) as unique_customers,
    SUM(sales) as total_sales
FROM filtered_data
WHERE product_id IN (SELECT product_id FROM top_products_global)
  AND city = 'CHERNIGIV';

-- 3.2: Alternative approach - city filter first, then calculate top products
WITH filtered_data_chernigiv AS (
    SELECT *
    FROM `b2b-recs.raw_data.tfrs_training_examples`
    WHERE date >= TIMESTAMP_SUB((SELECT MAX(date) FROM `b2b-recs.raw_data.tfrs_training_examples`), INTERVAL 60 DAY)
      AND city = 'CHERNIGIV'
),
top_products_chernigiv AS (
    SELECT product_id
    FROM (
        SELECT
            product_id,
            SUM(sales) as total_revenue,
            SUM(SUM(sales)) OVER () as grand_total,
            SUM(SUM(sales)) OVER (ORDER BY SUM(sales) DESC) as running_total
        FROM filtered_data_chernigiv
        GROUP BY product_id
    )
    WHERE running_total <= grand_total * 0.8
       OR running_total - total_revenue < grand_total * 0.8
)
SELECT
    'method_B_city_first_then_top' as approach,
    COUNT(*) as total_rows,
    COUNT(DISTINCT product_id) as unique_products,
    COUNT(DISTINCT customer_id) as unique_customers,
    SUM(sales) as total_sales
FROM filtered_data_chernigiv
WHERE product_id IN (SELECT product_id FROM top_products_chernigiv);

-- ============================================================================
-- TEST 4: Find products that differ between approaches
-- ============================================================================

-- Products in global top 80% but NOT in CHERNIGIV top 80%
WITH filtered_data AS (
    SELECT *
    FROM `b2b-recs.raw_data.tfrs_training_examples`
    WHERE date >= TIMESTAMP_SUB((SELECT MAX(date) FROM `b2b-recs.raw_data.tfrs_training_examples`), INTERVAL 60 DAY)
),
filtered_data_chernigiv AS (
    SELECT * FROM filtered_data WHERE city = 'CHERNIGIV'
),
top_products_global AS (
    SELECT product_id
    FROM (
        SELECT product_id, SUM(sales) as total_revenue,
            SUM(SUM(sales)) OVER () as grand_total,
            SUM(SUM(sales)) OVER (ORDER BY SUM(sales) DESC) as running_total
        FROM filtered_data
        GROUP BY product_id
    )
    WHERE running_total <= grand_total * 0.8
       OR running_total - total_revenue < grand_total * 0.8
),
top_products_chernigiv AS (
    SELECT product_id
    FROM (
        SELECT product_id, SUM(sales) as total_revenue,
            SUM(SUM(sales)) OVER () as grand_total,
            SUM(SUM(sales)) OVER (ORDER BY SUM(sales) DESC) as running_total
        FROM filtered_data_chernigiv
        GROUP BY product_id
    )
    WHERE running_total <= grand_total * 0.8
       OR running_total - total_revenue < grand_total * 0.8
)
SELECT
    'in_global_but_not_chernigiv_top80' as comparison,
    COUNT(*) as product_count
FROM top_products_global
WHERE product_id NOT IN (SELECT product_id FROM top_products_chernigiv)

UNION ALL

SELECT
    'in_chernigiv_but_not_global_top80' as comparison,
    COUNT(*) as product_count
FROM top_products_chernigiv
WHERE product_id NOT IN (SELECT product_id FROM top_products_global)

UNION ALL

SELECT
    'in_both_top80' as comparison,
    COUNT(*) as product_count
FROM top_products_global
WHERE product_id IN (SELECT product_id FROM top_products_chernigiv);

-- ============================================================================
-- TEST 5: Verify revenue coverage in each approach
-- ============================================================================

-- What percentage of CHERNIGIV revenue is covered by each top products set?
WITH filtered_data AS (
    SELECT *
    FROM `b2b-recs.raw_data.tfrs_training_examples`
    WHERE date >= TIMESTAMP_SUB((SELECT MAX(date) FROM `b2b-recs.raw_data.tfrs_training_examples`), INTERVAL 60 DAY)
),
filtered_data_chernigiv AS (
    SELECT * FROM filtered_data WHERE city = 'CHERNIGIV'
),
top_products_global AS (
    SELECT product_id
    FROM (
        SELECT product_id, SUM(sales) as total_revenue,
            SUM(SUM(sales)) OVER () as grand_total,
            SUM(SUM(sales)) OVER (ORDER BY SUM(sales) DESC) as running_total
        FROM filtered_data
        GROUP BY product_id
    )
    WHERE running_total <= grand_total * 0.8
       OR running_total - total_revenue < grand_total * 0.8
),
top_products_chernigiv AS (
    SELECT product_id
    FROM (
        SELECT product_id, SUM(sales) as total_revenue,
            SUM(SUM(sales)) OVER () as grand_total,
            SUM(SUM(sales)) OVER (ORDER BY SUM(sales) DESC) as running_total
        FROM filtered_data_chernigiv
        GROUP BY product_id
    )
    WHERE running_total <= grand_total * 0.8
       OR running_total - total_revenue < grand_total * 0.8
),
chernigiv_totals AS (
    SELECT SUM(sales) as total_revenue FROM filtered_data_chernigiv
)
SELECT
    'wizard_approach_global_top80' as method,
    ROUND(SUM(fdc.sales), 2) as revenue_covered,
    ROUND(SUM(fdc.sales) * 100.0 / (SELECT total_revenue FROM chernigiv_totals), 2) as percent_of_chernigiv_revenue
FROM filtered_data_chernigiv fdc
WHERE fdc.product_id IN (SELECT product_id FROM top_products_global)

UNION ALL

SELECT
    'alternative_chernigiv_top80' as method,
    ROUND(SUM(fdc.sales), 2) as revenue_covered,
    ROUND(SUM(fdc.sales) * 100.0 / (SELECT total_revenue FROM chernigiv_totals), 2) as percent_of_chernigiv_revenue
FROM filtered_data_chernigiv fdc
WHERE fdc.product_id IN (SELECT product_id FROM top_products_chernigiv);

-- ============================================================================
-- TEST 6: Verify the original wizard query row count
-- (This should match what the dataset wizard shows)
-- ============================================================================

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
    WHERE tfrs_training_examples.date >= TIMESTAMP_SUB((SELECT MAX(date) FROM `b2b-recs.raw_data.tfrs_training_examples`), INTERVAL 60 DAY)
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
)
SELECT
  'original_wizard_query' as source,
  COUNT(*) as total_rows,
  COUNT(DISTINCT product_id) as unique_products,
  COUNT(DISTINCT customer_id) as unique_customers,
  SUM(sales) as total_sales
FROM filtered_data
WHERE
  product_id IN (SELECT product_id FROM top_products) AND
  city IN ('CHERNIGIV');
