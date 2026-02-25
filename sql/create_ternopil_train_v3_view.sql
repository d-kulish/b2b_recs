-- Training view v3: all data EXCEPT the last day
-- Purpose: Training set that excludes the most recent day (used for evaluation)
-- v3: Based on tfrs_training_examples_v3_Ternopil (excludes OTHERS FD / OTHERS NF)

CREATE OR REPLACE VIEW `b2b-recs.raw_data.ternopil_train_v3` AS
SELECT *
FROM `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil`
WHERE DATE(date) < (
  SELECT MAX(DATE(date))
  FROM `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil`
);
