#!/usr/bin/env python3
"""DataExtractor Component with Product Metadata - Extracts last 90 days of data with product features"""

import argparse
import logging
import os
import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

import apache_beam as beam
import tensorflow as tf
from apache_beam.options.pipeline_options import PipelineOptions, GoogleCloudOptions, StandardOptions, WorkerOptions
from apache_beam.io.gcp.bigquery import ReadFromBigQuery
from google.cloud import storage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_bigquery_query(
    project_id: str,
    dataset_id: str,
    target_cities: List[str],
    start_date: str,
    end_date: str,
    sample_fraction: float = 1.0
) -> str:
    """Create BigQuery query for the specified date range with product metadata."""
    
    # Format cities for SQL IN clause
    cities_quoted = [f"'{city}'" for city in target_cities]
    cities_str = f"({', '.join(cities_quoted)})"
    
    logger.info(f"Extracting data from: {start_date} to {end_date}")
    
    return f"""
    WITH filtered_articles AS (
      -- Get latest product info, excluding OTHERS FD and OTHERS NF categories
      SELECT
        art_no,
        var_tu_key,
        (art_no * 1000000 + var_tu_key) AS product_id,
        art_name,
        stratbuy_domain_desc,
        mge_main_cat_desc,
        division_desc,
        ROW_NUMBER() OVER (PARTITION BY art_no, var_tu_key ORDER BY update_date DESC) as rn
      FROM
        `{project_id}.{dataset_id}.ml_bi_articles_tbl`
      WHERE
        division_desc NOT IN ('OTHERS FD', 'OTHERS NF')
    ),
    product_revenues AS (
      -- Calculate total revenue per product across all cities (excluding OTHERS categories)
      SELECT
        (invoices.art_no * 1000000 + invoices.var_tu_key) AS product_id,
        SUM(CAST(invoices.sell_val_nsp AS FLOAT64)) AS total_revenue
      FROM
        `{project_id}.{dataset_id}.ml_bi_invoices_tbl` AS invoices
      LEFT JOIN
        `{project_id}.{dataset_id}.ml_bi_stores_tbl` AS stores
      ON
        invoices.store_id = stores.store_id
      INNER JOIN
        filtered_articles AS articles
      ON
        invoices.art_no = articles.art_no
        AND invoices.var_tu_key = articles.var_tu_key
        AND articles.rn = 1
      WHERE
        invoices.date_of_day BETWEEN '{start_date}' AND '{end_date}'
        AND invoices.flag_cust_target_group = "SCO"
        AND invoices.sell_val_nsp > 0
        AND stores.city IN {cities_str}
      GROUP BY
        product_id
    ),
    ranked_products AS (
      -- Rank products by revenue
      SELECT
        product_id,
        total_revenue,
        ROW_NUMBER() OVER (ORDER BY total_revenue DESC, product_id) AS product_rank
      FROM
        product_revenues
    ),
    top_products AS (
      -- Select top 2000 products by revenue (covers ~62% of revenue, good balance)
      SELECT
        product_id
      FROM
        ranked_products
      WHERE
        product_rank <= 2000
    ),
    latest_product_info AS (
      -- Use filtered articles (already excluding OTHERS categories)
      SELECT
        product_id,
        art_name,
        stratbuy_domain_desc,
        mge_main_cat_desc
      FROM
        filtered_articles
      WHERE
        rn = 1
    ),
    active_customers AS (
      -- Filter customers with at least 3 distinct products (meaningful interaction history)
      SELECT
        cust_person_id
      FROM
        `{project_id}.{dataset_id}.ml_bi_invoices_tbl` AS invoices
      LEFT JOIN
        `{project_id}.{dataset_id}.ml_bi_stores_tbl` AS stores
      ON
        invoices.store_id = stores.store_id
      INNER JOIN
        top_products
      ON
        (invoices.art_no * 1000000 + invoices.var_tu_key) = top_products.product_id
      WHERE
        invoices.date_of_day BETWEEN '{start_date}' AND '{end_date}'
        AND invoices.flag_cust_target_group = "SCO"
        AND invoices.sell_val_nsp > 0
        AND stores.city IN {cities_str}
      GROUP BY
        cust_person_id
      HAVING
        COUNT(DISTINCT (invoices.art_no * 1000000 + invoices.var_tu_key)) > 2
    )
    -- Main query with customer total revenue, timestamp, and product metadata
    SELECT
      invoices.cust_person_id,
      (invoices.art_no * 1000000 + invoices.var_tu_key) AS product_id,
      SUM(CAST(invoices.sell_val_nsp AS FLOAT64)) OVER (PARTITION BY invoices.cust_person_id) AS revenue,
      stores.city,
      UNIX_SECONDS(TIMESTAMP(invoices.date_of_day)) AS timestamp,
      -- New product metadata fields with N/A for missing values
      COALESCE(prod.art_name, 'N/A') AS art_name,
      COALESCE(prod.stratbuy_domain_desc, 'N/A') AS stratbuy_domain_desc,
      COALESCE(prod.mge_main_cat_desc, 'N/A') AS mge_main_cat_desc
    FROM
      `{project_id}.{dataset_id}.ml_bi_invoices_tbl` AS invoices
    INNER JOIN
      active_customers
    ON
      invoices.cust_person_id = active_customers.cust_person_id
    LEFT JOIN
      `{project_id}.{dataset_id}.ml_bi_stores_tbl` AS stores
    ON
      invoices.store_id = stores.store_id
    INNER JOIN
      top_products
    ON
      (invoices.art_no * 1000000 + invoices.var_tu_key) = top_products.product_id
    LEFT JOIN
      latest_product_info AS prod
    ON
      (invoices.art_no * 1000000 + invoices.var_tu_key) = prod.product_id
    WHERE
      invoices.date_of_day BETWEEN '{start_date}' AND '{end_date}'
      AND invoices.flag_cust_target_group = "SCO"
      AND invoices.sell_val_nsp > 0
      AND stores.city IN {cities_str}
      AND MOD(ABS(FARM_FINGERPRINT(CAST(invoices.cust_person_id AS STRING))), 100) < {int(sample_fraction * 100)}
    ORDER BY
      revenue DESC, invoices.cust_person_id, product_id
    """


def dict_to_tf_example(row_dict: Dict[str, Any]):
    """Convert BigQuery row to tf.Example with product metadata."""
    import tensorflow as tf
    
    feature_dict = {}
    
    # String features (including new product metadata)
    for key in ['cust_person_id', 'city', 'art_name', 'stratbuy_domain_desc', 'mge_main_cat_desc']:
        if key in row_dict and row_dict[key] is not None:
            feature_dict[key] = tf.train.Feature(
                bytes_list=tf.train.BytesList(value=[str(row_dict[key]).encode('utf-8')])
            )
    
    # Integer features
    for key in ['product_id', 'timestamp']:
        if key in row_dict and row_dict[key] is not None:
            feature_dict[key] = tf.train.Feature(
                int64_list=tf.train.Int64List(value=[int(row_dict[key])])
            )
    
    # Float features - customer total revenue
    for key in ['revenue']:
        if key in row_dict and row_dict[key] is not None:
            feature_dict[key] = tf.train.Feature(
                float_list=tf.train.FloatList(value=[float(row_dict[key])])
            )
    
    return tf.train.Example(features=tf.train.Features(feature=feature_dict))


class CountExamples(beam.CombineFn):
    """Count total examples in single dataset."""
    
    def create_accumulator(self):
        return 0
    
    def add_input(self, accumulator, element):
        return accumulator + 1
    
    def merge_accumulators(self, accumulators):
        return sum(accumulators)
    
    def extract_output(self, accumulator):
        return accumulator


class LogSampleExamplesDoFn(beam.DoFn):
    """DoFn to log sample examples for verification."""
    
    def __init__(self, num_samples: int = 5):
        self.num_samples = num_samples
        self.logged_count = 0
        # Configure logger for DoFn
        import logging
        self.logger = logging.getLogger(__name__)
    
    def process(self, element):
        # Log first few examples
        if self.logged_count < self.num_samples:
            self.logger.info(f"\n=== SAMPLE DATASET EXAMPLE {self.logged_count + 1} ===")
            
            # Parse the tf.Example to show readable data
            import tensorflow as tf
            example = tf.train.Example()
            example.ParseFromString(element.SerializeToString())
            
            for feature_name, feature in example.features.feature.items():
                if feature.bytes_list.value:
                    value = feature.bytes_list.value[0].decode('utf-8')
                elif feature.int64_list.value:
                    value = feature.int64_list.value[0]
                elif feature.float_list.value:
                    value = feature.float_list.value[0]
                else:
                    value = "empty"
                
                self.logger.info(f"  {feature_name}: {value}")
            
            self.logged_count += 1
        
        yield element


class SaveMetadataDoFn(beam.DoFn):
    """DoFn to save metadata about the extracted dataset with product features."""
    
    def __init__(self, output_path: str, project_id: str, dataset_id: str, 
                 target_cities: List[str], sample_fraction: float,
                 start_date: str,
                 end_date: str):
        self.output_path = output_path
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.start_date = start_date
        self.end_date = end_date
        self.target_cities = target_cities
        self.sample_fraction = sample_fraction
        # Configure logger for DoFn
        import logging
        self.logger = logging.getLogger(__name__)
    
    def process(self, total_count):
        import json
        import os
        from google.cloud import storage
        
        # Single dataset count
        total_examples = total_count
        
        # Build dataset info
        dataset_info = {
            'project_id': self.project_id,
            'dataset_id': self.dataset_id,
            'target_cities': self.target_cities,
            'sample_fraction': self.sample_fraction,
            'extraction_type': 'recent_days_with_product_metadata',
            'period': {
                'start_date': self.start_date,
                'end_date': self.end_date
            },
            'description': f'Recent data with product metadata: {self.start_date} to {self.end_date}'
        }
        
        metadata = {
            'dataset_info': dataset_info,
            'total_examples': total_examples,
            'data_pattern': f"{self.output_path}/all_data/data-*.tfrecord.gz",
            'features': {
                'cust_person_id': {'dtype': 'string'},
                'product_id': {'dtype': 'int64'},
                'revenue': {'dtype': 'float32', 'description': 'Customer total revenue across all transactions'},
                'city': {'dtype': 'string'},
                'timestamp': {'dtype': 'int64', 'description': 'Unix timestamp from date_of_day for temporal patterns'},
                # New product features
                'art_name': {'dtype': 'string', 'description': 'Product name in local language'},
                'stratbuy_domain_desc': {'dtype': 'string', 'description': 'Product category (66 unique values)'},
                'mge_main_cat_desc': {'dtype': 'string', 'description': 'Product sub-category (427 unique values)'}
            },
            'splitting_methodology': 'single_dataset_for_functional_splitting'
        }
        
        # LOG METADATA BEFORE SAVING
        self.logger.info("\n" + "=" * 70)
        self.logger.info("📊 DATASET METADATA WITH PRODUCT FEATURES:")
        self.logger.info("=" * 70)
        
        # Log dataset info
        self.logger.info("🔧 DATASET CONFIGURATION:")
        for key, value in dataset_info.items():
            self.logger.info(f"  {key}: {value}")
        
        # Log dataset statistics
        self.logger.info("\n📈 SINGLE DATASET:")
        self.logger.info(f"  Total examples: {total_examples:,}")
        self.logger.info(f"  Output location: {self.output_path}/all_data/")
        self.logger.info(f"  Splitting: Will be done functionally in trainer (80/15/5)")
        
        # Log features schema
        self.logger.info("\n🏗️ FEATURES SCHEMA:")
        for feature_name, feature_info in metadata['features'].items():
            dtype = feature_info['dtype']
            description = feature_info.get('description', 'No description')
            self.logger.info(f"  {feature_name}: {dtype} - {description}")
        
        self.logger.info("=" * 70)
        
        # Save metadata to GCS
        metadata_path = f"{self.output_path}/metadata.json"
        
        if metadata_path.startswith('gs://'):
            # Extract bucket and blob path
            path_parts = metadata_path[5:].split('/', 1)
            bucket_name = path_parts[0]
            blob_path = path_parts[1] if len(path_parts) > 1 else ''
            
            client = storage.Client(project=self.project_id)
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            blob.upload_from_string(json.dumps(metadata, indent=2))
        else:
            # Local file system
            os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
        
        print(f"Metadata saved to: {metadata_path}")
        yield f"Metadata saved to: {metadata_path}"


def run_dataextractor_pipeline(
    project_id: str,
    region: str,
    dataset_id: str,
    target_cities: List[str],
    output_path: str,
    sample_fraction: float = 1.0,
    runner: str = 'DirectRunner',
    num_days: int = 90,
    execution_date: Optional[str] = None,
    num_workers: int = 2,
    max_num_workers: int = 20,
    worker_machine_type: str = 'n1-standard-4'
):
    """Run the DataExtractor pipeline for recent days with product metadata."""
    
    logger.info(f"Starting DataExtractor with Product Metadata pipeline for {target_cities}")
    
    # Parse execution date or use current date
    if execution_date:
        exec_date = datetime.strptime(execution_date, "%Y-%m-%d")
    else:
        exec_date = datetime.now()
    
    logger.info(f"Execution date: {exec_date.strftime('%Y-%m-%d')}")
    
    # Calculate period (last N days from execution date)
    end_date = exec_date
    start_date = exec_date - timedelta(days=num_days)
    
    # Format dates for BigQuery
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    logger.info(f"Extraction period: {start_str} to {end_str} ({num_days} days)")
    
    # Configure pipeline options
    pipeline_options = PipelineOptions()
    google_cloud_options = pipeline_options.view_as(GoogleCloudOptions)
    google_cloud_options.project = project_id
    google_cloud_options.region = region
    google_cloud_options.staging_location = f"gs://metro_recs3/staging"
    google_cloud_options.temp_location = f"gs://metro_recs3/temp"
    
    pipeline_options.view_as(StandardOptions).runner = runner
    
    # Add network and autoscaling configuration for Dataflow
    if runner == 'DataflowRunner':
        worker_options = pipeline_options.view_as(WorkerOptions)
        worker_options.subnetwork = f"regions/{region}/subnetworks/default"
        worker_options.use_public_ips = False
        
        # CRITICAL: Add autoscaling for large datasets
        # Use parameters for flexible configuration
        worker_options.num_workers = num_workers  # Initial workers
        worker_options.max_num_workers = max_num_workers  # Max for autoscaling
        worker_options.autoscaling_algorithm = 'THROUGHPUT_BASED'
        
        # Use configurable machine type
        worker_options.machine_type = worker_machine_type
        
        # Disk configuration for large datasets
        worker_options.disk_size_gb = 100  # Increase disk size
        # Note: disk_type is not directly settable via WorkerOptions
        # Dataflow will use the default disk type (pd-standard)
        
        logger.info(f"Dataflow autoscaling: {num_workers}-{max_num_workers} workers, {worker_machine_type} machines")
    
    # Create pipeline
    with beam.Pipeline(options=pipeline_options) as pipeline:
        
        # Read from BigQuery
        raw_data = (
            pipeline
            | 'ReadFromBigQuery' >> beam.io.ReadFromBigQuery(
                query=create_bigquery_query(
                    project_id=project_id,
                    dataset_id=dataset_id,
                    target_cities=target_cities,
                    start_date=start_str,
                    end_date=end_str,
                    sample_fraction=sample_fraction
                ),
                use_standard_sql=True,
                project=project_id
            )
        )
        
        # Convert all data to TensorFlow examples
        all_examples = raw_data | 'ConvertToExamples' >> beam.Map(dict_to_tf_example)
        
        # Count total examples
        total_count = (all_examples
                      | 'CountAllExamples' >> beam.CombineGlobally(CountExamples()))
        
        # Add sample logging before serialization
        examples_with_logging = (all_examples 
            | 'LogSampleExamples' >> beam.ParDo(LogSampleExamplesDoFn(5)))
        
        # Write all examples to single folder
        (examples_with_logging
         | 'SerializeExamples' >> beam.Map(lambda x: x.SerializeToString())
         | 'WriteAllExamples' >> beam.io.WriteToTFRecord(
             f"{output_path}/all_data/data",
             file_name_suffix='.tfrecord.gz',
             compression_type=beam.io.filesystem.CompressionTypes.GZIP,
             num_shards=25
         ))
        
        # Save metadata with total count
        _ = (total_count
             | 'SaveMetadata' >> beam.ParDo(SaveMetadataDoFn(
                 output_path=output_path,
                 project_id=project_id,
                 dataset_id=dataset_id,
                 target_cities=target_cities,
                 sample_fraction=sample_fraction,
                 start_date=start_str,
                 end_date=end_str
             )))
    
    logger.info("DataExtractor with Product Metadata pipeline completed successfully")


def main():
    """Main entry point for data extraction with product metadata."""
    
    try:
        parser = argparse.ArgumentParser(description='Metro Recommender DataExtractor Component with Product Metadata')
        parser.add_argument('--project_id', required=True, help='Google Cloud project ID')
        parser.add_argument('--region', required=True, help='Google Cloud region')
        parser.add_argument('--dataset_id', required=True, help='BigQuery dataset ID')
        parser.add_argument('--target_cities', required=True, nargs='+', help='Target city names')
        parser.add_argument('--output_path', required=True, help='GCS output path')
        parser.add_argument('--sample_fraction', type=float, default=1.0, help='Data sampling fraction')
        parser.add_argument('--runner', default='DirectRunner', help='Beam runner (DirectRunner/DataflowRunner)')
        parser.add_argument('--num_days', type=int, default=90, help='Number of days to extract')
        parser.add_argument('--execution_date', help='Execution date in YYYY-MM-DD format (default: today)')
        
        # Dataflow worker configuration arguments
        parser.add_argument('--num_workers', type=int, default=2, help='Initial number of Dataflow workers')
        parser.add_argument('--max_num_workers', type=int, default=20, help='Maximum number of workers for autoscaling')
        parser.add_argument('--worker_machine_type', default='n1-standard-4', help='Machine type for Dataflow workers')
        
        args = parser.parse_args()
        
        # Validate inputs
        if args.sample_fraction <= 0 or args.sample_fraction > 1:
            raise ValueError(f"Sample fraction must be between 0 and 1, got {args.sample_fraction}")
        
        if not args.output_path.startswith('gs://'):
            raise ValueError(f"Output path must be a GCS path starting with gs://, got {args.output_path}")
        
        logger.info(f"Starting DataExtractor with Product Metadata with parameters:")
        logger.info(f"  Project: {args.project_id}")
        logger.info(f"  Region: {args.region}")
        logger.info(f"  Dataset: {args.dataset_id}")
        logger.info(f"  Target cities: {args.target_cities}")
        logger.info(f"  Output path: {args.output_path}")
        logger.info(f"  Sample fraction: {args.sample_fraction}")
        logger.info(f"  Runner: {args.runner}")
        logger.info(f"  Days to extract: {args.num_days}")
        logger.info(f"  Execution date: {args.execution_date or 'today'}")
        
        # Run the pipeline
        run_dataextractor_pipeline(
            project_id=args.project_id,
            region=args.region,
            dataset_id=args.dataset_id,
            target_cities=args.target_cities,
            output_path=args.output_path,
            sample_fraction=args.sample_fraction,
            runner=args.runner,
            num_days=args.num_days,
            execution_date=args.execution_date,
            num_workers=args.num_workers,
            max_num_workers=args.max_num_workers,
            worker_machine_type=args.worker_machine_type
        )
        
        logger.info("DataExtractor with Product Metadata completed successfully")
        
    except Exception as e:
        logger.error(f"DataExtractor with Product Metadata failed: {str(e)}")
        import traceback
        traceback.print_exc()
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()