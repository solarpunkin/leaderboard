import os
import json
import time
from confluent_kafka import Consumer
from google.cloud import storage
from common.count_min_sketch import CountMinSketch
import google.auth
import google.auth.transport.requests

# --- Configuration ---
KAFKA_BROKERS = os.environ.get('KAFKA_BROKERS')
KAFKA_TOPIC = os.environ.get('KAFKA_TOPIC', 'leaderboard_events')
GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME')
SKETCH_STATE_KEY = 'state/cms_state.json'

# --- CMS Configuration ---
CMS_WIDTH = 1000
CMS_DEPTH = 5

# --- GCP Clients ---
storage_client = storage.Client()
creds, project = google.auth.default(scopes=['https://www.googleapis.com/auth/kafka'])

def oauth_cb(oauth_config):
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return creds.token, int(time.time() + 3600)

def load_sketch():
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(SKETCH_STATE_KEY)
    sketch = CountMinSketch(width=CMS_WIDTH, depth=CMS_DEPTH)

    try:
        state_data = blob.download_as_string()
        state = json.loads(state_data)
        sketch.sketch = state
        print("Loaded existing Count-Min Sketch from GCS.")
    except Exception as e:
        print(f"Could not load sketch, creating a new one: {e}")

    return sketch

def save_sketch(sketch):
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(SKETCH_STATE_KEY)
    blob.upload_from_string(json.dumps(sketch.sketch))
    print(f"Saved Count-Min Sketch state to GCS bucket {GCS_BUCKET_NAME}.")

def process_events():
    sketch = load_sketch()

    consumer_config = {
        'bootstrap.servers': KAFKA_BROKERS,
        'security.protocol': 'SASL_SSL',
        'sasl.mechanisms': 'OAUTHBEARER',
        'oauth_cb': oauth_cb,
        'group.id': 'realtime-processor-group',
        'auto.offset.reset': 'earliest'
    }

    consumer = Consumer(consumer_config)

    consumer.subscribe([KAFKA_TOPIC])
    print("Starting Kafka consumer for real-time processing...")

    processed_count = 0
    try:
        while True:
            msg = consumer.poll(1.0)

            if msg is None:
                continue
            if msg.error():
                print(f"Consumer error: {msg.error()}")
                continue

            event = json.loads(msg.value().decode('utf-8'))
            sketch.add(event['event_id'])
            processed_count += 1

            # Periodically save the sketch
            if processed_count % 100 == 0:
                save_sketch(sketch)

    except KeyboardInterrupt:
        pass
    finally:
        save_sketch(sketch)
        consumer.close()

if __name__ == '__main__':
    process_events()