-- Test view v3: only the last day of data
-- Purpose: Held-out evaluation set with data the model hasn't seen during training
-- v3: Based on tfrs_training_examples_v3_Ternopil (excludes OTHERS FD / OTHERS NF)

CREATE OR REPLACE VIEW `b2b-recs.raw_data.ternopil_test_v3` AS
SELECT *
FROM `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil`
WHERE DATE(date) = (
  SELECT MAX(DATE(date))
  FROM `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil`
);
