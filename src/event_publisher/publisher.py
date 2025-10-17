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

creds, project = google.auth.default(scopes=['https://www.googleapis.com/auth/kafka'])

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
        'oauth_cb': oauth_cb
    }

    producer = Producer(producer_config)

    print("Publishing events...")
    try:
        while True:
            event_id = str(uuid.uuid4())
            data = {'event_id': event_id}
            
            # produce() is non-blocking. It adds the message to a local buffer.
            # The delivery_report callback will be triggered from poll() below.
            producer.produce(KAFKA_TOPIC, key=event_id, value=json.dumps(data), callback=delivery_report)
            
            # poll() serves delivery reports (callbacks) from previous produce() calls.
            producer.poll(0)
            
            time.sleep(0.1) # Sleep briefly to prevent a tight loop from consuming 100% CPU
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        # Wait for any outstanding messages to be delivered and delivery reports to be received.
        producer.flush()

if __name__ == '__main__':
    main()
