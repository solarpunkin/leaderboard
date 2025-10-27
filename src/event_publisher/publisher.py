import os
import json
import uuid
import time
from google.cloud import pubsub_v1

# --- Configuration ---
GCP_PROJECT_ID = os.environ.get('GCP_PROJECT_ID')
PUBSUB_TOPIC_ID = os.environ.get('PUBSUB_TOPIC_ID', 'leaderboard_events')

def main():
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(GCP_PROJECT_ID, PUBSUB_TOPIC_ID)

    print(f"Publishing events to {topic_path}...")
    msg_count = 0
    try:
        while True:
            event_id = str(uuid.uuid4())
            data = {'event_id': event_id}
            message_json = json.dumps(data)
            
            # Data must be a bytestring
            future = publisher.publish(topic_path, message_json.encode("utf-8"))
            future.add_done_callback(callback)
            msg_count += 1

            if msg_count % 100 == 0:
                print(f"Published {msg_count} messages.")
            time.sleep(0.1) # Small delay to avoid overwhelming the system

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        print("Publisher stopped.")

def callback(future):
    message_id = future.result()
    # Optional: print for verbosity
    # print(f"Published message with ID: {message_id}")

if __name__ == '__main__':
    main()
