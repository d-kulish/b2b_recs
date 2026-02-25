-- Drop and recreate the Ternopil single-city table from tfrs_training_examples_v3
-- Purpose: Cost-efficient table for experiments (avoids querying the full view)
-- v3: Excludes OTHERS FD and OTHERS NF divisions

DROP TABLE IF EXISTS `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil`;

CREATE TABLE `b2b-recs.raw_data.tfrs_training_examples_v3_Ternopil` AS
SELECT *
FROM `b2b-recs.raw_data.tfrs_training_examples_v3`
WHERE city = 'TERNOPIL';
