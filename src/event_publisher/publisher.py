import json
import os
import time
import uuid

def publish_event(event_id, event_type):
    """
    Simulates publishing an event to the Kafka queue.

    An event is a JSON object with an event_id, type, timestamp, and a unique message_id.
    It's written to a file in the kafka_events directory.
    """
    event = {
        'message_id': str(uuid.uuid4()),
        'event_id': event_id,
        'event_type': event_type,
        'timestamp': int(time.time())
    }
    
    kafka_dir = os.path.join(os.path.dirname(__file__), '../../data/kafka_events')
    if not os.path.exists(kafka_dir):
        os.makedirs(kafka_dir)
        
    file_path = os.path.join(kafka_dir, f"{event['message_id']}.json")
    
    with open(file_path, 'w') as f:
        json.dump(event, f)
        
    print(f"Published event: {event}")

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Publish an event.')
    parser.add_argument('event_id', type=str, help='The ID of the event (e.g., song_id, product_id).')
    parser.add_argument('--event_type', type=str, default='view', help='The type of the event (e.g., view, click).')
    
    args = parser.parse_args()
    
    publish_event(args.event_id, args.event_type)
