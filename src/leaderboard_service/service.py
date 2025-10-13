import os
from flask import Flask, jsonify, request
from google.cloud import storage
import pyarrow.parquet as pq
from collections import Counter
import heapq
from common.count_min_sketch import CountMinSketch

app = Flask(__name__)

# --- Configuration ---
GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME')
SKETCH_STATE_KEY = 'state/cms_state.json'

# --- GCP Clients ---
storage_client = storage.Client()

# --- CMS Configuration ---
CMS_WIDTH = 1000
CMS_DEPTH = 5

def get_top_k(k=10):
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    blobs = bucket.list_blobs(prefix='batches/')

    total_counts = Counter()

    for blob in blobs:
        if blob.name.endswith('.parquet'):
            with blob.open("rb") as f:
                table = pq.read_table(f)
                df = table.to_pandas()
                for index, row in df.iterrows():
                    total_counts[row['event_id']] += row['count']

    # Use a min-heap to find the top K
    min_heap = []
    for event_id, count in total_counts.items():
        if len(min_heap) < k:
            heapq.heappush(min_heap, (count, event_id))
        else:
            if count > min_heap[0][0]:
                heapq.heapreplace(min_heap, (count, event_id))

    top_k = sorted(min_heap, key=lambda x: x[0], reverse=True)
    return [{'event_id': event_id, 'count': count} for count, event_id in top_k]

@app.route('/leaderboard', methods=['GET'])
def leaderboard():
    k = request.args.get('k', default=10, type=int)
    top_k = get_top_k(k)
    return jsonify(top_k)

@app.route('/leaderboard/approximate', methods=['GET'])
def approximate():
    event_ids_str = request.args.get('event_ids')
    if not event_ids_str:
        return jsonify({"error": "event_ids query parameter is required"}), 400

    event_ids = event_ids_str.split(',')

    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(SKETCH_STATE_KEY)
    sketch = CountMinSketch(width=CMS_WIDTH, depth=CMS_DEPTH)

    try:
        state_data = blob.download_as_string()
        state = json.loads(state_data)
        sketch.sketch = state
    except Exception as e:
        return jsonify({"error": f"Could not load sketch from GCS: {e}"}), 500

    results = {eid: sketch.estimate(eid) for eid in event_ids}
    return jsonify(results)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
