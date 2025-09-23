import json
import os
import sys

# Add common directory to path to import CountMinSketch
sys.path.append(os.path.join(os.path.dirname(__file__), '../common'))
from count_min_sketch import CountMinSketch

# --- Configuration ---
KAFKA_DIR = os.path.join(os.path.dirname(__file__), '../../data/kafka_events')
TS_DB_DIR = os.path.join(os.path.dirname(__file__), '../../data/ts_db')
PROCESSED_LOG_FILE = os.path.join(TS_DB_DIR, 'processed_log.txt')
SKETCH_STATE_FILE = os.path.join(TS_DB_DIR, 'cms_state.json')

# CMS parameters
CMS_WIDTH = 1000
CMS_DEPTH = 5

def load_sketch():
    """Loads the Count-Min Sketch from the state file, or creates a new one."""
    if not os.path.exists(TS_DB_DIR):
        os.makedirs(TS_DB_DIR)

    sketch = CountMinSketch(width=CMS_WIDTH, depth=CMS_DEPTH)
    if os.path.exists(SKETCH_STATE_FILE):
        with open(SKETCH_STATE_FILE, 'r') as f:
            sketch.sketch = json.load(f)
        print("Loaded existing Count-Min Sketch from state.")
    else:
        print("Created a new Count-Min Sketch.")
    return sketch

def save_sketch(sketch):
    """Saves the sketch's state to a file."""
    with open(SKETCH_STATE_FILE, 'w') as f:
        json.dump(sketch.sketch, f)
    print(f"Saved Count-Min Sketch state to {SKETCH_STATE_FILE}")

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

def process_events():
    """
    Processes new events from the Kafka directory, updates the sketch, and logs processed files.
    """
    sketch = load_sketch()
    processed_files = get_processed_files()
    
    events_processed = 0
    newly_processed = []

    for filename in sorted(os.listdir(KAFKA_DIR)):
        if not filename.endswith('.json') or filename in processed_files:
            continue

        file_path = os.path.join(KAFKA_DIR, filename)
        
        try:
            with open(file_path, 'r') as f:
                event = json.load(f)
            
            sketch.add(event['event_id'])
            events_processed += 1
            newly_processed.append(filename)
            print(f"Processed event: {event['message_id']} for event_id: {event['event_id']}")

        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error processing file {filename}: {e}")

    if events_processed > 0:
        save_sketch(sketch)
        for filename in newly_processed:
            log_processed_file(filename)
    else:
        print("No new events to process.")

if __name__ == '__main__':
    process_events()
