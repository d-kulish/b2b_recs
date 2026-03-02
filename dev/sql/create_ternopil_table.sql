-- Drop and recreate the Ternopil single-city table from tfrs_training_examples_v2
-- Purpose: Cost-efficient table for experiments (avoids querying the full view)

DROP TABLE IF EXISTS `b2b-recs.raw_data.tfrs_training_examples_v2_Ternopil`;

CREATE TABLE `b2b-recs.raw_data.tfrs_training_examples_v2_Ternopil` AS
SELECT *
FROM `b2b-recs.raw_data.tfrs_training_examples_v2`
WHERE city = 'TERNOPIL';
