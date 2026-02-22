-- Training view: all data EXCEPT the last day
-- Purpose: Training set that excludes the most recent day (used for evaluation)

CREATE OR REPLACE VIEW `b2b-recs.raw_data.ternopil_train` AS
SELECT *
FROM `b2b-recs.raw_data.tfrs_training_examples_v2_Ternopil`
WHERE DATE(date) < (
  SELECT MAX(DATE(date))
  FROM `b2b-recs.raw_data.tfrs_training_examples_v2_Ternopil`
);
