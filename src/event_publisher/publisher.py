import os
import json
import uuid
import time
from confluent_kafka import Producer
import google.auth
import google.auth.transport.requests

# --- Configuration ---
KAFKA_BROKERS = os.environ.get('KAFKA_BROKERS')
KAFKA_TOPIC = os.environ.get('KAFKA_TOPIC', 'leaderboard_events')

creds, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])

def oauth_cb(oauth_config):
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return creds.token, int(time.time() + 3600)

def main():
    producer_config = {
        'bootstrap.servers': KAFKA_BROKERS,
        'security.protocol': 'SASL_SSL',
        'sasl.mechanisms': 'OAUTHBEARER',
        'sasl.oauthbearer.config': oauth_cb
    }

    producer = Producer(producer_config)

    while True:
        event_id = str(uuid.uuid4())
        data = {'event_id': event_id}
        producer.produce(KAFKA_TOPIC, key=event_id, value=json.dumps(data))
        producer.flush()
        print(f"Published event {event_id} to topic {KAFKA_TOPIC}")
        time.sleep(1)

if __name__ == '__main__':
    main()
