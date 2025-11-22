import os
from flask import Flask, jsonify, request
from google.cloud import storage
import pyarrow.parquet as pq
import os
import json
from flask import Flask, jsonify, request
import redis
from common.count_min_sketch import CountMinSketch

from datetime import datetime, timedelta
import uuid
import time
import threading

from cachetools import cached, TTLCache
from cachetools.keys import hashkey

app = Flask(__name__)

# --- Configuration ---
GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME')
SKETCH_STATE_KEY = 'state/cms_state.json'
REDIS_HOST = os.environ.get('REDIS_HOST')
REDIS_PORT = os.environ.get('REDIS_PORT')

# --- In-Memory Caches ---
# Cache for the main leaderboard endpoint. Results are cached for 10 seconds.
leaderboard_cache = TTLCache(maxsize=128, ttl=10)

# This cache holds the sketch data to avoid hitting GCS on every approximate query.
# It's stored per-worker (per pod replica). A shared cache like Redis would be overkill
# for this approximate data, and this per-worker cache is simpler and has no cost.
sketch_cache = {
    "sketch": None,
    "expiry_time": 0,
    "lock": threading.Lock()
}
CACHE_TTL_SECONDS = 60

# --- Clients ---
storage_client = storage.Client()
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, ssl=True, ssl_cert_reqs=None)

# --- CMS Configuration ---
CMS_WIDTH = 1000
CMS_DEPTH = 5

@app.route('/leaderboard', methods=['GET'])
@cached(leaderboard_cache, key=lambda: hashkey(request.args.get('hours', default=1, type=int), request.args.get('k', default=10, type=int)))
def leaderboard():
    try:
        hours = request.args.get('hours', type=int)
        k = request.args.get('k', default=10, type=int)

        if hours is None:
            # For a cumulative, all-time leaderboard, we would need a separate key.
            # This implementation focuses on time-windowed queries.
            # We can return the most recent hour as a default.
            hours = 1

        # 1. Generate the list of Redis keys for the last X hours
        keys_to_fetch = []
        now = datetime.utcnow()
        for i in range(hours):
            target_time = now - timedelta(hours=i)
            keys_to_fetch.append(target_time.strftime("leaderboard:%Y-%m-%d-%H"))
        
        if not keys_to_fetch:
            return jsonify([])

        # 2. Use Redis to aggregate the scores from all those keys into a temporary key
        temp_agg_key = f"temp_agg:{uuid.uuid4()}"
        redis_client.zunionstore(temp_agg_key, keys_to_fetch, aggregate='SUM')
        
        # 3. Get the Top-K from the temporary aggregated set
        top_k_raw = redis_client.zrevrange(temp_agg_key, 0, k - 1, withscores=True)
        
        # 4. Clean up the temporary key
        redis_client.delete(temp_agg_key)
        
        # 5. Format and return the result
        return jsonify([{'event_id': item[0], 'count': int(item[1])} for item in top_k_raw])
    except Exception as e:
        # Log the error and return a server error
        app.logger.error(f"Error in leaderboard endpoint: {e}")
        return jsonify({"error": "An internal error occurred"}), 500

def get_sketch_from_cache():
    """Gets the CMS sketch, updating from GCS if the cache is expired."""
    with sketch_cache["lock"]:
        if time.time() > sketch_cache["expiry_time"]:
            try:
                bucket = storage_client.bucket(GCS_BUCKET_NAME)
                blob = bucket.blob(SKETCH_STATE_KEY)
                state_data = blob.download_as_string()
                state = json.loads(state_data)
                
                sketch = CountMinSketch(width=CMS_WIDTH, depth=CMS_DEPTH)
                sketch.sketch = state
                
                sketch_cache["sketch"] = sketch
                sketch_cache["expiry_time"] = time.time() + CACHE_TTL_SECONDS
                print("CMS Sketch cache updated from GCS.")
            except Exception as e:
                # If GCS fetch fails, continue to use the old cache but log the error
                print(f"Error updating CMS sketch cache: {e}")
                # Extend expiry to avoid constant GCS hammering on failure
                sketch_cache["expiry_time"] = time.time() + 15 

    return sketch_cache["sketch"]

@app.route('/leaderboard/approximate', methods=['GET'])
def approximate():
    event_ids_str = request.args.get('event_ids')
    if not event_ids_str:
        return jsonify({"error": "event_ids query parameter is required"}), 400

    sketch = get_sketch_from_cache()
    if not sketch:
        return jsonify({"error": "CMS Sketch not available. Please try again shortly."}), 503

    event_ids = event_ids_str.split(',')
    results = {eid: sketch.estimate(eid) for eid in event_ids}
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

