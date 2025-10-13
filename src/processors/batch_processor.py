import os
import json
import time
from collections import Counter
from confluent_kafka import Consumer
from google.cloud import storage
import pyarrow as pa
import pyarrow.parquet as pq
import google.auth
import google.auth.transport.requests

# --- Configuration ---
KAFKA_BROKERS = os.environ.get('KAFKA_BROKERS')
KAFKA_TOPIC = os.environ.get('KAFKA_TOPIC', 'leaderboard_events')
GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME')

# --- GCP Clients ---
storage_client = storage.Client()
creds, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])

def oauth_cb(oauth_config):
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return creds.token, int(time.time() + 3600)

def process_batch():
    consumer_config = {
        'bootstrap.servers': KAFKA_BROKERS,
        'security.protocol': 'SASL_SSL',
        'sasl.mechanisms': 'OAUTHBEARER',
        'sasl.oauthbearer.config': oauth_cb,
        'group.id': 'batch-processor-group',
        'auto.offset.reset': 'earliest'
    }

    consumer = Consumer(consumer_config)

    consumer.subscribe([KAFKA_TOPIC])
    print("Starting Kafka consumer for batch processing...")

    batch_counts = Counter()
    message_count = 0
    
    # Consume for a limited time to form a batch
    end_time = time.time() + 60 # Consume for 60 seconds
    while time.time() < end_time:
        msg = consumer.poll(1.0)

        if msg is None:
            continue
        if msg.error():
            print(f"Consumer error: {msg.error()}")
            continue

        event = json.loads(msg.value().decode('utf-8'))
        batch_counts[event['event_id']] += 1
        message_count += 1

    consumer.close()

    if message_count > 0:
        output_data = [{'event_id': eid, 'count': c} for eid, c in batch_counts.items()]
        batch_timestamp = int(time.time())
        output_key = f'batches/batch_{batch_timestamp}.parquet'

        # Create a PyArrow Table
        table = pa.Table.from_pylist(output_data)

        # Write to GCS
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(output_key)
        
        with blob.open("wb") as f:
            pq.write_table(table, f)

        print(f"Saved batch file to gs://{GCS_BUCKET_NAME}/{output_key}")
    else:
        print("No messages in batch.")

if __name__ == '__main__':
    process_batch()