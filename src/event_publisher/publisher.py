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

creds, project = google.auth.default()

def oauth_cb(oauth_config):
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return creds.token, int(time.time() + 3600)

def delivery_report(err, msg):
    """ Called once for each message produced to indicate delivery result.
        Triggered by poll() or flush(). """
    if err is not None:
        print(f'Message delivery failed: {err}')
    else:
        # Optional: print for verbosity
        # print(f'Message delivered to {msg.topic()} [{msg.partition()}]')
        pass

def main():
    producer_config = {
        'bootstrap.servers': KAFKA_BROKERS,
        'security.protocol': 'SASL_SSL',
        'sasl.mechanisms': 'OAUTHBEARER',
        'oauth_cb': oauth_cb,
        'acks': 'all'
    }

    producer = Producer(producer_config)

    print("Publishing events...")
    msg_count = 0
    try:
        while True:
            event_id = str(uuid.uuid4())
            data = {'event_id': event_id}
            producer.produce(KAFKA_TOPIC, key=event_id, value=json.dumps(data), callback=delivery_report)
            msg_count += 1

            # The non-blocking poll is for serving callbacks quickly.
            producer.poll(0)

            # Periodically call flush() to block and wait for deliveries.
            # This is what gives the client time to complete its auth handshake.
            if msg_count % 100 == 0:
                print(f"Flushing producer after {msg_count} messages...")
                producer.flush(5) # Block for up to 5 seconds

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        print("Performing final flush...")
        producer.flush()

if __name__ == '__main__':
    main()
