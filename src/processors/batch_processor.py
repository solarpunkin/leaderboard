import json
import os
import time
from collections import Counter

# --- Configuration ---
KAFKA_DIR = os.path.join(os.path.dirname(__file__), '../../data/kafka_events')
HDFS_DIR = os.path.join(os.path.dirname(__file__), '../../data/hdfs_storage')
PROCESSED_LOG_FILE = os.path.join(HDFS_DIR, 'processed_log.txt')

def get_processed_files():
    """Reads the set of already processed file names from the log."""
    if not os.path.exists(PROCESSED_LOG_FILE):
        return set()
    with open(PROCESSED_LOG_FILE, 'r') as f:
        return set(line.strip() for line in f)

def log_processed_file(filename):
    """Appends a processed file name to the log."""
    with open(PROCESSED_LOG_FILE, 'a') as f:
        f.write(filename + '\n')

def process_batch():
    """
    Simulates a batch processing job (like Spark).
    - Reads new events from the queue.
    - Computes exact counts for the batch.
    - Saves the result to a new batch file in the HDFS simulation dir.
    - Logs the files it has processed.
    """
    if not os.path.exists(HDFS_DIR):
        os.makedirs(HDFS_DIR)

    processed_files = get_processed_files()
    batch_counts = Counter()
    newly_processed = []

    print("Starting batch processing...")
    for filename in sorted(os.listdir(KAFKA_DIR)):
        if not filename.endswith('.json') or filename in processed_files:
            continue

        file_path = os.path.join(KAFKA_DIR, filename)
        try:
            with open(file_path, 'r') as f:
                event = json.load(f)
            
            batch_counts[event['event_id']] += 1
            newly_processed.append(filename)
            print(f"Read event {event['message_id']} for event_id: {event['event_id']}")

        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error processing file {filename}: {e}")

    if newly_processed:
        # Format the output
        output_data = [{'event_id': event_id, 'count': count} for event_id, count in batch_counts.items()]
        
        # Save the batch result to a new file
        batch_timestamp = int(time.time())
        output_filename = os.path.join(HDFS_DIR, f'batch_{{batch_timestamp}}.json')
        with open(output_filename, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        print(f"Batch processing complete. Result saved to {output_filename}")

        # Update the log of processed files
        for filename in newly_processed:
            log_processed_file(filename)
    else:
        print("No new events for batch processing.")

if __name__ == '__main__':
    process_batch()
