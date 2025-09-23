import json
import os
import sys
import heapq

# Add common directory to path to import CountMinSketch
sys.path.append(os.path.join(os.path.dirname(__file__), '../common'))
from count_min_sketch import CountMinSketch

# --- Configuration ---
TS_DB_DIR = os.path.join(os.path.dirname(__file__), '../../data/ts_db')
SKETCH_STATE_FILE = os.path.join(TS_DB_DIR, 'cms_state.json')
HDFS_DIR = os.path.join(os.path.dirname(__file__), '../../data/hdfs_storage')

# CMS parameters (must match the processor's config)
CMS_WIDTH = 1000
CMS_DEPTH = 5

def get_unique_event_ids():
    """
    Scans the processed events directory to find all unique event IDs.
    In a real system, this might come from a metadata store or an event registry.
    """
    # This is a simple simulation. We check both kafka processed logs.
    processed_log_files = [
        os.path.join(TS_DB_DIR, 'processed_log.txt'),
        os.path.join(HDFS_DIR, 'processed_log.txt')
    ]
    processed_files = set()
    for log_file in processed_log_files:
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                processed_files.update(line.strip() for line in f)

    kafka_dir = os.path.join(os.path.dirname(__file__), '../../data/kafka_events')
    event_ids = set()
    for filename in processed_files:
        if not filename.endswith('.json'):
            continue
        file_path = os.path.join(kafka_dir, filename)
        if not os.path.exists(file_path):
            continue
        try:
            with open(file_path, 'r') as f:
                event = json.load(f)
            if 'event_id' in event:
                event_ids.add(event['event_id'])
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Could not read event_id from {filename}: {e}")
    
    print(f"Discovered unique event IDs: {list(event_ids)}")
    return list(event_ids)

def get_approximate_top_k(k):
    """
    Calculates the top K leaderboard from the approximate pipeline.
    """
    if not os.path.exists(SKETCH_STATE_FILE):
        print("Error: Count-Min Sketch state file not found.")
        return []

    # Load the sketch
    sketch = CountMinSketch(width=CMS_WIDTH, depth=CMS_DEPTH)
    with open(SKETCH_STATE_FILE, 'r') as f:
        sketch.sketch = json.load(f)
    print("Loaded Count-Min Sketch from state.")

    # Get all items and their estimates
    event_ids = get_unique_event_ids()
    if not event_ids:
        print("No event IDs found to estimate.")
        return []

    estimates = []
    for event_id in event_ids:
        count = sketch.estimate(event_id)
        estimates.append((event_id, count))
        print(f"Estimated count for '{event_id}': {count}")

    # Use a min-heap to find the top K elements efficiently
    top_k = heapq.nlargest(k, estimates, key=lambda item: item[1])
    
    return top_k

def get_exact_top_k(k):
    """
    Calculates the top K leaderboard from the exact batch pipeline.
    It aggregates results from all available batch files.
    """
    if not os.path.exists(HDFS_DIR):
        print("Error: HDFS storage directory not found.")
        return []

    total_counts = Counter()
    batch_files_found = 0
    for filename in os.listdir(HDFS_DIR):
        if not filename.startswith('batch_') or not filename.endswith('.json'):
            continue
        
        file_path = os.path.join(HDFS_DIR, filename)
        batch_files_found += 1
        print(f"Reading batch file: {filename}")
        with open(file_path, 'r') as f:
            batch_data = json.load(f)
            for item in batch_data:
                total_counts[item['event_id']] += item['count']

    if batch_files_found == 0:
        print("No batch files found to generate exact leaderboard.")
        return []

    print(f"Aggregated counts: {dict(total_counts)}")
    top_k = total_counts.most_common(k)
    return top_k

if __name__ == '__main__':
    import argparse
    from collections import Counter

    parser = argparse.ArgumentParser(description='Get the top K leaderboard.')
    parser.add_argument('--mode', type=str, default='approximate', choices=['approximate', 'exact'], help='The type of leaderboard to query.')
    parser.add_argument('-k', type=int, default=5, help='The number of top elements to return.')
    
    args = parser.parse_args()
    
    if args.mode == 'approximate':
        # First, let's run the realtime processor to make sure the CMS is up-to-date
        # In a real system this would be a continuously running service.
        print("Running real-time processor to update sketch...")
        os.system('python3 src/processors/realtime_processor.py')
        print("---------------------------------------------")

        top_k_results = get_approximate_top_k(args.k)
        print("\n--- Approximate Top K Leaderboard ---")
        if top_k_results:
            for i, (event_id, count) in enumerate(top_k_results):
                print(f"{i+1}. Event: '{event_id}', Estimated Count: {count}")
        else:
            print("Leaderboard is empty.")
    
    else: # mode == 'exact'
        top_k_results = get_exact_top_k(args.k)
        print("\n--- Exact Top K Leaderboard ---")
        if top_k_results:
            for i, (event_id, count) in enumerate(top_k_results):
                print(f"{i+1}. Event: '{event_id}', Exact Count: {count}")
        else:
            print("Leaderboard is empty.")
