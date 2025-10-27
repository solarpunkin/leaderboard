import os
import json
import time
from google.cloud import pubsub_v1
from google.cloud import storage
from common.count_min_sketch import CountMinSketch

# --- Configuration ---
GCP_PROJECT_ID = os.environ.get('GCP_PROJECT_ID')
PUBSUB_SUBSCRIPTION_ID = os.environ.get('PUBSUB_SUBSCRIPTION_ID')
GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME')
SKETCH_STATE_KEY = 'state/cms_state.json'

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
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(GCP_PROJECT_ID, PUBSUB_SUBSCRIPTION_ID)

    print(f"Listening for messages on {subscription_path}...")

    processed_count = 0

    def callback(message):
        nonlocal processed_count
        try:
            event = json.loads(message.data.decode('utf-8'))
            sketch.add(event['event_id'])
            processed_count += 1

            # Periodically save the sketch
            if processed_count % 100 == 0:
                save_sketch(sketch)
            message.ack()
        except Exception as e:
            print(f"Error processing message: {e}")
            message.nack() # Nack the message to re-deliver it later

    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    
    # Wrap subscriber in a try/finally block to automatically call close() when done.
    try:
        # When timeout is unspecified, the result method waits indefinitely.
        streaming_pull_future.result()
    except KeyboardInterrupt:
        streaming_pull_future.cancel()
        streaming_pull_future.result() # Block until the shutdown is complete
    finally:
        save_sketch(sketch)
        subscriber.close()

if __name__ == '__main__':
    process_events()