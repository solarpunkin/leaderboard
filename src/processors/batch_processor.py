import os
import json
import time
from collections import Counter
from confluent_kafka import Consumer
import redis
import google.auth
import google.auth.transport.requests

# --- Configuration ---
KAFKA_BROKERS = os.environ.get('KAFKA_BROKERS')
KAFKA_TOPIC = os.environ.get('KAFKA_TOPIC', 'leaderboard_events')
REDIS_HOST = os.environ.get('REDIS_HOST')
REDIS_PORT = os.environ.get('REDIS_PORT')

# --- GCP Clients ---
creds, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

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
        print(f"Updating Redis leaderboard with {len(batch_counts)} events.")
        # Use a pipeline to send commands in a single transaction
        pipe = redis_client.pipeline()
        for event_id, count in batch_counts.items():
            pipe.zadd('leaderboard', {event_id: count}, incr=True)
        pipe.execute()
        print(f"Successfully updated Redis leaderboard.")
    else:
        print("No messages in batch.")

if __name__ == '__main__':
    process_batch()