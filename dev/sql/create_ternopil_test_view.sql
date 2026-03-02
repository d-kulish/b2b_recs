-- Test view: only the last day of data
-- Purpose: Held-out evaluation set with data the model hasn't seen during training

CREATE OR REPLACE VIEW `b2b-recs.raw_data.ternopil_test` AS
SELECT *
FROM `b2b-recs.raw_data.tfrs_training_examples_v2_Ternopil`
WHERE DATE(date) = (
  SELECT MAX(DATE(date))
  FROM `b2b-recs.raw_data.tfrs_training_examples_v2_Ternopil`
);
