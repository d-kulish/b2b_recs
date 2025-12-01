# Metro Recommender Production Pipeline v2
# GPU Priority: T4 -> V100 -> L4 (optimized for availability)
# Key Features:
# - Early stopping monitors regularization_loss (more stable than val_loss)
# - Adaptive learning rate reduction on plateau (patience=4)
# - Model checkpointing saves best model based on regularization_loss
# - No warmup steps to allow LR reduction callback to work

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

# Configuration
PROJECT_ID = 'cf-mccuagcf-recommenders-ht'
REGION = 'europe-west4'
BUCKET_NAME = 'metro_recs3'
ARTIFACT_REGISTRY = f'{REGION}-docker.pkg.dev/{PROJECT_ID}/metro-recs-repo'
SERVICE_ACCOUNT = '1032729337493-compute@developer.gserviceaccount.com'

default_args = {
    'owner': 'metro-recommender',
    'depends_on_past': False,
    'start_date': datetime(2025, 7, 1),
    'email_on_failure': False,
    'retries': 0,
}

dag = DAG(
    'metro_recommender_production_v2',
    default_args=default_args,
    description='Production Metro Recommender Pipeline v2 with Early Stopping on regularization_loss & Adaptive LR Reduction',
    schedule_interval='0 3 2 * *',  # Run at 3 AM on the 2nd day of every month
    catchup=False,
    max_active_runs=1,
    tags=['ml-pipeline', 'production'],
)

# Define paths using Airflow templates - using data_interval_end for correct monthly dating
data_path = f'gs://{BUCKET_NAME}/production/{{{{ data_interval_end.strftime("%Y%m%d") }}}}_{{{{ run_id[:8] }}}}/raw_data'
vocab_path = f'gs://{BUCKET_NAME}/production/{{{{ data_interval_end.strftime("%Y%m%d") }}}}_{{{{ run_id[:8] }}}}/vocabularies'
model_path = f'gs://{BUCKET_NAME}/production/{{{{ data_interval_end.strftime("%Y%m%d") }}}}_{{{{ run_id[:8] }}}}/models'

# Step 1: Data Extraction
data_task = BashOperator(
    task_id='data_extractor',
    bash_command=f'''
    echo "🔵 Starting Data Extraction..."
    echo "Output path: {data_path}"

    CURRENT_DATE="{{{{ data_interval_end.strftime('%Y-%m-%d') }}}}"
    ACTUAL_DATE=$(date +%Y-%m-%d)
    echo "📅 Execution date (ds): {{{{ ds }}}}"
    echo "📅 Data interval end: $CURRENT_DATE"
    echo "📅 Actual run date: $ACTUAL_DATE"

    # Calculate age of execution date
    DAYS_DIFF=$(( ($(date -d "$ACTUAL_DATE" +%s) - $(date -d "$CURRENT_DATE" +%s)) / 86400 ))
    if [ $DAYS_DIFF -gt 7 ]; then
        echo "⚠️  WARNING: This is a backfill run! Execution date is $DAYS_DIFF days in the past."
        echo "⚠️  Training will use historical data from $CURRENT_DATE, not current data."
    fi
    
    JOB_OUTPUT=$(gcloud ai custom-jobs create \
        --region={REGION} \
        --display-name=data-{{{{ ds_nodash }}}}_{{{{ run_id[:8] }}}} \
        --worker-pool-spec=replica-count=1,machine-type=n1-standard-4,container-image-uri={ARTIFACT_REGISTRY}/data-extractor:latest \
        --args="--project_id","{PROJECT_ID}","--region","{REGION}","--dataset_id","segmentation","--target_cities","KIROVOHRAD","LUTSK","TERNOPIL","CHERNIGIV","ZHYTOMYR","ODESA","KRYVYY RIH","VINNYTSYA","MYKOLAIV","POLTAVA","IVANO-FRANKIVSK","CHERNIVTSI","RIVNE","LVIV","MARIUPOL","KHARKIV","DNIPROPETROVSK","ZAPORIZHZHYA","KYIV","--output_path","{data_path}","--sample_fraction","1.0","--runner","DataflowRunner","--num_days","90","--execution_date","$CURRENT_DATE","--num_workers","4","--max_num_workers","20","--worker_machine_type","n1-standard-8" \
        --service-account={SERVICE_ACCOUNT} \
        --project={PROJECT_ID} \
        --format="value(name)")
    
    JOB_ID=$(echo $JOB_OUTPUT | awk -F'/' '{{print $NF}}')
    echo "📋 Created job: $JOB_ID"
    
    echo "⏳ Waiting for data extraction to complete..."
    WAIT_COUNT=0
    while true; do
        STATE=$(gcloud ai custom-jobs describe $JOB_ID --region={REGION} --format="value(state)")
        WAIT_COUNT=$((WAIT_COUNT + 1))
        echo "[$WAIT_COUNT] Job state: $STATE"
        
        if [[ "$STATE" == "JOB_STATE_SUCCEEDED" ]]; then
            echo "✅ Data extraction completed successfully!"
            break
        elif [[ "$STATE" == "JOB_STATE_FAILED" ]] || [[ "$STATE" == "JOB_STATE_CANCELLED" ]]; then
            echo "❌ Data extraction failed or was cancelled!"
            gcloud ai custom-jobs describe $JOB_ID --region={REGION}
            exit 1
        fi
        
        sleep 30
    done
    
    echo "🔍 Verifying output..."
    if gsutil ls {data_path}/all_data/data-*.tfrecord.gz | head -1; then
        echo "✅ Dataset files found"
        TOTAL_EXAMPLES=$(gsutil cat {data_path}/metadata.json | grep -o '"total_examples": [0-9]*' | grep -o '[0-9]*')
        echo "📊 Total examples extracted: $TOTAL_EXAMPLES"
    else
        echo "❌ No dataset files found"
        exit 1
    fi
    ''',
    dag=dag,
)

# Step 2: Vocabulary Builder
vocab_task = BashOperator(
    task_id='vocab_builder',
    bash_command=f'''
    echo "🟡 Starting Vocabulary Building..."
    echo "Input path: {data_path}/all_data/*.tfrecord.gz"
    echo "Output path: {vocab_path}"
    
    JOB_OUTPUT=$(gcloud ai custom-jobs create \
        --region={REGION} \
        --display-name=vocab-{{{{ ds_nodash }}}}_{{{{ run_id[:8] }}}} \
        --worker-pool-spec=replica-count=1,machine-type=n1-standard-4,container-image-uri={ARTIFACT_REGISTRY}/vocab_builder:latest \
        --args="--input_path","{data_path}/all_data/*.tfrecord.gz","--output_path","{vocab_path}","--num_revenue_buckets","1000","--num_timestamp_buckets","90" \
        --service-account={SERVICE_ACCOUNT} \
        --project={PROJECT_ID} \
        --format="value(name)")
    
    JOB_ID=$(echo $JOB_OUTPUT | awk -F'/' '{{print $NF}}')
    echo "📋 Created job: $JOB_ID"
    
    echo "⏳ Waiting for vocabulary building to complete..."
    WAIT_COUNT=0
    while true; do
        STATE=$(gcloud ai custom-jobs describe $JOB_ID --region={REGION} --format="value(state)")
        WAIT_COUNT=$((WAIT_COUNT + 1))
        echo "[$WAIT_COUNT] Job state: $STATE"
        
        if [[ "$STATE" == "JOB_STATE_SUCCEEDED" ]]; then
            echo "✅ Vocabulary building completed successfully!"
            break
        elif [[ "$STATE" == "JOB_STATE_FAILED" ]] || [[ "$STATE" == "JOB_STATE_CANCELLED" ]]; then
            echo "❌ Vocabulary building failed or was cancelled!"
            gcloud ai custom-jobs describe $JOB_ID --region={REGION}
            exit 1
        fi
        
        sleep 30
    done
    
    echo "🔍 Verifying vocabulary output..."
    if gsutil ls {vocab_path}/vocabularies.json; then
        echo "✅ Vocabulary file found"
        PRODUCTS=$(gsutil cat {vocab_path}/vocabularies.json | grep -o '"products": [0-9]*' | grep -o '[0-9]*')
        CUSTOMERS=$(gsutil cat {vocab_path}/vocabularies.json | grep -o '"customers": [0-9]*' | grep -o '[0-9]*')
        echo "📊 Products: $PRODUCTS, Customers: $CUSTOMERS"
    else
        echo "❌ Vocabulary file not found"
        exit 1
    fi
    ''',
    dag=dag,
)

# Step 3: GPU Training - 150 epochs production with early stopping
trainer_task = BashOperator(
    task_id='trainer_gpu_v2',
    bash_command=f'''
    echo "🟠 Starting GPU Training v2 with Early Stopping (max 150 epochs)..."
    echo "TFRecords path: {data_path}/all_data/*.tfrecord.gz"
    echo "Vocabularies path: {vocab_path}/vocabularies.json"
    echo "Output path: {model_path}"
    echo "🆕 Using trainer-v2 with early stopping on regularization_loss (patience=7), adaptive LR reduction (patience=4), and model checkpointing"
    
    # Try T4 GPUs first (most available)
    echo "🚀 Attempting with 4x T4 GPUs (best availability)..."
    JOB_OUTPUT=$(gcloud ai custom-jobs create \
        --region={REGION} \
        --display-name=trainer-{{{{ ds_nodash }}}}_{{{{ run_id[:8] }}}} \
        --worker-pool-spec=replica-count=1,machine-type=n1-standard-32,accelerator-type=NVIDIA_TESLA_T4,accelerator-count=4,container-image-uri={ARTIFACT_REGISTRY}/trainer-v2:latest \
        --args="--tfrecords-path","{data_path}/all_data/*.tfrecord.gz","--vocabularies-path","{vocab_path}/vocabularies.json","--metadata-path","{data_path}/metadata.json","--output-path","{model_path}","--epochs","150","--learning-rate","0.001","--batch-size","1024","--lr-scaling","sqrt","--early-stopping-patience","7","--reduce-lr-patience","4","--min-epochs","10" \
        --service-account={SERVICE_ACCOUNT} \
        --project={PROJECT_ID} \
        --format="value(name)" 2>&1)
    
    if [ $? -ne 0 ]; then
        echo "⚠️ T4 GPUs unavailable, trying 4x V100..."
        
        # Try V100 GPUs
        JOB_OUTPUT=$(gcloud ai custom-jobs create \
            --region={REGION} \
            --display-name=trainer-{{{{ ds_nodash }}}}_{{{{ run_id[:8] }}}} \
            --worker-pool-spec=replica-count=1,machine-type=n1-standard-16,accelerator-type=NVIDIA_TESLA_V100,accelerator-count=4,container-image-uri={ARTIFACT_REGISTRY}/trainer-v2:latest \
            --args="--tfrecords-path","{data_path}/all_data/*.tfrecord.gz","--vocabularies-path","{vocab_path}/vocabularies.json","--metadata-path","{data_path}/metadata.json","--output-path","{model_path}","--epochs","150","--learning-rate","0.001","--batch-size","2048","--lr-scaling","sqrt","--early-stopping-patience","7","--reduce-lr-patience","4","--min-epochs","10" \
            --service-account={SERVICE_ACCOUNT} \
            --project={PROJECT_ID} \
            --format="value(name)" 2>&1)
        
        if [ $? -ne 0 ]; then
            echo "⚠️ V100 GPUs unavailable, trying 4x L4..."
            
            # Try L4 GPUs
            JOB_OUTPUT=$(gcloud ai custom-jobs create \
                --region={REGION} \
                --display-name=trainer-{{{{ ds_nodash }}}}_{{{{ run_id[:8] }}}} \
                --worker-pool-spec=replica-count=1,machine-type=g2-standard-48,accelerator-type=NVIDIA_L4,accelerator-count=4,container-image-uri={ARTIFACT_REGISTRY}/trainer-v2:latest \
                --args="--tfrecords-path","{data_path}/all_data/*.tfrecord.gz","--vocabularies-path","{vocab_path}/vocabularies.json","--metadata-path","{data_path}/metadata.json","--output-path","{model_path}","--epochs","150","--learning-rate","0.001","--batch-size","2048","--lr-scaling","sqrt","--early-stopping-patience","7","--reduce-lr-patience","4","--min-epochs","10" \
                --service-account={SERVICE_ACCOUNT} \
                --project={PROJECT_ID} \
                --format="value(name)" 2>&1)
            
            if [ $? -ne 0 ]; then
                echo "⚠️ L4 GPUs unavailable, trying 2x T4 as final fallback..."
                
                # Final fallback: 2x T4
                JOB_OUTPUT=$(gcloud ai custom-jobs create \
                    --region={REGION} \
                    --display-name=trainer-{{{{ ds_nodash }}}}_{{{{ run_id[:8] }}}} \
                    --worker-pool-spec=replica-count=1,machine-type=n1-standard-16,accelerator-type=NVIDIA_TESLA_T4,accelerator-count=2,container-image-uri={ARTIFACT_REGISTRY}/trainer-v2:latest \
                    --args="--tfrecords-path","{data_path}/all_data/*.tfrecord.gz","--vocabularies-path","{vocab_path}/vocabularies.json","--metadata-path","{data_path}/metadata.json","--output-path","{model_path}","--epochs","150","--learning-rate","0.001","--batch-size","512","--lr-scaling","sqrt","--early-stopping-patience","7","--reduce-lr-patience","4","--min-epochs","10" \
                    --service-account={SERVICE_ACCOUNT} \
                    --project={PROJECT_ID} \
                    --format="value(name)" 2>&1)
                
                if [ $? -ne 0 ]; then
                    echo "❌ No GPUs available. Error:"
                    echo "$JOB_OUTPUT"
                    exit 1
                fi
            fi
        fi
    fi
    
    JOB_ID=$(echo $JOB_OUTPUT | awk -F'/' '{{print $NF}}')
    
    if [ -z "$JOB_ID" ]; then
        echo "❌ Failed to extract job ID"
        exit 1
    fi
    
    echo "📋 Created job: $JOB_ID"
    
    echo "⏳ Waiting for training to complete (max 150 epochs with early stopping)..."
    WAIT_COUNT=0
    while true; do
        STATE=$(gcloud ai custom-jobs describe $JOB_ID --region={REGION} --format="value(state)")
        WAIT_COUNT=$((WAIT_COUNT + 1))
        ELAPSED_MIN=$(($WAIT_COUNT / 2))
        echo "[$WAIT_COUNT] Job state: $STATE ($ELAPSED_MIN minutes elapsed)"
        
        if [[ "$STATE" == "JOB_STATE_SUCCEEDED" ]]; then
            echo "✅ Training completed successfully!"
            break
        elif [[ "$STATE" == "JOB_STATE_FAILED" ]] || [[ "$STATE" == "JOB_STATE_CANCELLED" ]]; then
            echo "❌ Training failed or was cancelled!"
            gcloud ai custom-jobs describe $JOB_ID --region={REGION}
            exit 1
        fi
        
        sleep 30
    done
    
    echo "🔍 Verifying model output..."
    if gsutil ls {model_path}/saved_model/saved_model.pb && gsutil ls {model_path}/query_model/saved_model.pb && gsutil ls {model_path}/candidate_model/saved_model.pb; then
        echo "✅ All 3 models found!"
    else
        echo "❌ Model verification failed"
        exit 1
    fi
    ''',
    dag=dag,
)

# Step 4: Cloud Run Deployment
deploy_task = BashOperator(
    task_id='cloud_deploy',
    bash_command=f'''
    echo "🚀 Starting Cloud Run Deployment..."
    echo "Model path: {model_path}"
    echo "Vocab path: {vocab_path}/vocabularies.json"
    echo "Execution date: {{{{ ds }}}}"
    echo "Actual run date: $(date +%Y-%m-%d)"

    # Extract model date from path and validate freshness
    MODEL_DATE=$(echo "{model_path}" | grep -oP '\\d{{8}}' | head -1)
    CURRENT_DATE=$(date +%Y%m%d)

    if [ -n "$MODEL_DATE" ]; then
        DAYS_OLD=$(( ($(date -d "$CURRENT_DATE" +%s) - $(date -d "$MODEL_DATE" +%s)) / 86400 ))
        echo "📅 Model date: $MODEL_DATE (Age: $DAYS_OLD days)"

        if [ $DAYS_OLD -gt 7 ]; then
            echo "⚠️  WARNING: Model is $DAYS_OLD days old!"
            echo "⚠️  This suggests a backfill/catchup run rather than a fresh model."
            echo "⚠️  Proceeding with deployment, but please verify this is intentional."
            echo "⚠️  For production, consider triggering a manual run with current date."
        elif [ $DAYS_OLD -lt 0 ]; then
            echo "⚠️  WARNING: Model date is in the future! This is unexpected."
        else
            echo "✅ Model is fresh ($DAYS_OLD days old)"
        fi
    else
        echo "⚠️  WARNING: Could not extract model date from path"
    fi

    echo "🔍 Verifying model artifacts..."
    if ! gsutil ls {model_path}/saved_model/saved_model.pb; then
        echo "❌ saved_model.pb missing!"
        exit 1
    fi
    
    echo "🚢 Deploying to Cloud Run..."
    gcloud run deploy metro-recommender \
        --image {ARTIFACT_REGISTRY}/metro-batch:latest \
        --set-env-vars MODEL_BASE_PATH={model_path},VOCAB_PATH={vocab_path}/vocabularies.json \
        --platform managed \
        --region {REGION} \
        --memory 4Gi \
        --cpu 2 \
        --timeout 600 \
        --concurrency 10 \
        --max-instances 5 \
        --cpu-throttling \
        --cpu-boost \
        --min-instances=1 \
        --project {PROJECT_ID}
    
    if [ $? -eq 0 ]; then
        echo "✅ Cloud Run deployment completed!"
    else
        echo "❌ Cloud Run deployment failed"
        exit 1
    fi
    
    SERVICE_URL="https://metro-recommender-1032729337493.europe-west4.run.app"
    echo "🌐 Service URL: $SERVICE_URL"
    echo "✅ Deployment successful!"
    ''',
    dag=dag,
)

# Dependencies
data_task >> vocab_task >> trainer_task >> deploy_task